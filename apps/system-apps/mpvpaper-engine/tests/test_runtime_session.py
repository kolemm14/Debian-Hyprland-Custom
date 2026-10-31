"""Mock integration: no real compositor, subprocess, credentials or assets."""
import json
from contextlib import closing
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpvpaper_engine.config import EngineConfig, load_config, save_config
from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.runtimes.runtime_manager import RuntimeManager
from mpvpaper_engine.systemd import runtime_description
from mpvpaper_engine.library import Library, SCHEMA


class FakeSystemd:
    def __init__(self):
        self.units = {}
        self.stops = []
    def unit_status(self, output):
        return self.units.get(output, {}).get('state', 'inactive')
    def details(self, output):
        return self.units.get(output, {'state': 'inactive', 'process': 0, 'exit_code': 0, 'description': ''}).copy()
    def stop_checked(self, output):
        self.stops.append(output)
        self.units.pop(output, None)
    def launch(self, output, path, runtime):
        self.units[output] = {'state': 'active', 'process': 99, 'exit_code': 0,
                              'description': runtime_description(runtime, path)}


class RuntimeSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.paths = EnginePaths.from_environment({'HOME':str(self.root), 'XDG_CONFIG_HOME':str(self.root/'cfg'),
            'XDG_DATA_HOME':str(self.root/'data'), 'XDG_CACHE_HOME':str(self.root/'cache'), 'XDG_RUNTIME_DIR':str(self.root/'run')})
        self.config = EngineConfig()
        self.video = self.root/'test.mp4'; self.video.touch()
        self.image = self.root/'test.png'; self.image.touch()
        self.scene = self.root/'scene'; self.scene.mkdir()
        (self.scene/'scene.pkg').touch()
        (self.scene/'project.json').write_text(json.dumps({'type':'scene','file':'scene.pkg'}))
        self.connected = ['eDP-1','HDMI-A-1']
        self.systemd = FakeSystemd()
        self.mpv = Mock()
        def mpv_start(screen, project):
            self.systemd.launch(screen, project.path, 'mpvpaper')
            return 'systemd'
        self.mpv.start.side_effect = mpv_start
        self.lwe = Mock()
        self.lwe.command.side_effect = lambda output, project, fps: [str(project.path)]
        self.lwe.start_command.side_effect = lambda output, command: self.systemd.launch(output, command[-1], 'linux-wallpaperengine')
        self.manager = self.new_manager()
        patcher=patch('shutil.which', side_effect=lambda name: name);patcher.start();self.addCleanup(patcher.stop)

    def new_manager(self):
        return RuntimeManager(mpv=self.mpv,lwe=self.lwe,systemd=self.systemd,
            config=self.config,paths=self.paths,persist=True,
            monitor_detector=lambda:[SimpleNamespace(name=n) for n in self.connected])

    def test_mixed_apply_and_inverse(self):
        self.manager.apply('eDP-1',self.video)
        self.manager.apply('HDMI-A-1',self.scene)
        result=self.manager.apply('*')
        self.assertTrue(all(v['ok'] for v in result.values()))
        self.assertEqual(self.lwe.start_command.call_count,1)
        self.manager.apply('eDP-1',self.scene)
        self.manager.apply('HDMI-A-1',self.image)
        self.assertEqual(self.manager.status('eDP-1')['runtime'],'linux-wallpaperengine')
        self.assertEqual(self.manager.status('HDMI-A-1')['project_type'],'image')
        self.assertEqual(len(self.systemd.units),2)

    def test_one_failure_does_not_undo_other(self):
        self.config.outputs={'eDP-1':{'wallpaper':str(self.video)},'HDMI-A-1':{'wallpaper':str(self.root/'missing')}}
        result=self.manager.apply_all()
        self.assertTrue(result['eDP-1']['ok']);self.assertFalse(result['HDMI-A-1']['ok'])
        self.assertEqual(self.systemd.unit_status('eDP-1'),'active')

    def test_crash_status_and_no_cross_screen_stop(self):
        self.manager.apply('eDP-1',self.video);self.manager.apply('HDMI-A-1',self.scene)
        self.systemd.units['HDMI-A-1'].update(state='failed',process=0,exit_code=2)
        self.assertEqual(self.manager.status('HDMI-A-1')['exit_code'],2)
        self.manager.stop('HDMI-A-1');self.manager.stop('HDMI-A-1')
        self.assertEqual(self.systemd.unit_status('eDP-1'),'active')

    def test_restore_intentions_without_process_identifiers(self):
        self.manager.apply('eDP-1',self.video);self.manager.apply('HDMI-A-1',self.scene)
        self.assertNotIn('process',self.paths.config_file.read_text())
        self.assertNotIn('PID',self.paths.config_file.read_text())
        self.manager.stop_all(remember=False)
        self.config=load_config(self.paths);manager=self.new_manager()
        self.assertTrue(all(v['ok'] for v in manager.restore().values()))
        self.assertEqual(len(self.systemd.units),2)
        calls=self.lwe.start_command.call_count
        manager.restore()
        self.assertEqual(self.lwe.start_command.call_count,calls)

    def test_hotplug_preserves_assignment_and_restores(self):
        self.manager.apply('eDP-1',self.video);self.manager.apply('HDMI-A-1',self.scene)
        self.manager.restore();self.connected.remove('HDMI-A-1')
        self.manager.reconcile()
        self.assertEqual(self.systemd.unit_status('HDMI-A-1'),'inactive')
        self.assertTrue(self.config.outputs['HDMI-A-1']['enabled'])
        self.connected.append('HDMI-A-1');self.manager.reconcile()
        self.assertEqual(self.systemd.unit_status('HDMI-A-1'),'active')

    def test_missing_monitor_is_not_reassigned(self):
        self.config.outputs={'HDMI-A-1':{'wallpaper':str(self.scene),'enabled':True}}
        self.connected=['eDP-1'];self.manager.restore()
        self.assertEqual(self.systemd.units,{})
        self.assertIn('HDMI-A-1',self.config.outputs)

    def test_web_never_restored(self):
        (self.scene/'project.json').write_text(json.dumps({'type':'web','file':'scene.pkg'}))
        self.config.outputs={'eDP-1':{'wallpaper':str(self.scene),'enabled':True,'runtime':'linux-wallpaperengine'}}
        self.assertFalse(self.manager.restore()['eDP-1']['ok'])
        self.lwe.start_command.assert_not_called()

    def test_stop_disables_restore(self):
        self.manager.apply('eDP-1',self.video);self.manager.stop('*');self.manager.restore()
        self.assertEqual(self.systemd.units,{})

    def test_changed_options_replaces_scene(self):
        self.manager.apply('eDP-1',self.scene,fps=30)
        self.manager.apply('eDP-1',self.scene,fps=60)
        self.assertEqual(self.lwe.start_command.call_count,2)

    def test_library_registers_whole_project_and_favorites(self):
        library=Library(self.paths)
        item=library.import_project(self.scene)
        self.assertEqual(item.path,self.scene)
        self.assertEqual(item.media_type.value,'scene')
        library.set_favorite(item.id,True)
        self.assertTrue(library.get(item.id).favorite)
        self.assertTrue((self.scene/'scene.pkg').exists())
        self.assertEqual(library.import_project(self.scene).id,item.id)

    def test_database_migration_preserves_references(self):
        import sqlite3
        self.paths.data_home.mkdir(parents=True)
        with closing(sqlite3.connect(self.paths.library_db)) as conn:
            conn.executescript(SCHEMA.replace("'image', 'video', 'scene', 'web'", "'image', 'video'"))
            conn.execute("INSERT INTO wallpapers(id,path,title,type,file_size,mtime_ns,fingerprint,date_added,favorite) VALUES(7,'/old.mp4','old','video',0,0,'x','2026-01-01T00:00:00Z',1)")
            conn.execute("INSERT INTO history(wallpaper_id,output,started_at) VALUES(7,'eDP-1','2026-01-01T00:00:00Z')")
            conn.commit()
        library=Library(self.paths);library.initialize();library.import_project(self.scene)
        self.assertTrue(library.get(7).favorite)
        with closing(sqlite3.connect(self.paths.library_db)) as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(conn.execute('SELECT wallpaper_id FROM history').fetchone()[0],7)

    def test_gui_scene_uses_ipc_and_skips_media_theme_extraction(self):
        from mpvpaper_engine.gui_backend import GuiBackend
        client=Mock();client.play.return_value={'strategy':'linux-wallpaperengine', 'persisted':True}
        theme=Mock()
        backend=GuiBackend(self.paths,client=client,theme_sync=theme,library_roots=(self.root,))
        item=backend.import_project(self.scene)
        backend.apply(item.id,'eDP-1')
        client.play.assert_called_once_with('eDP-1',str(self.scene))
        theme.apply.assert_not_called()

    def test_scan_does_not_import_scene_previews(self):
        (self.scene/'preview.png').write_bytes(b'not a wallpaper')
        library=Library(self.paths)
        library.scan([self.scene])
        self.assertEqual([p.media_type.value for p in library.list()],['scene'])

    def test_no_lwe_calls_when_all_outputs_use_mpv(self):
        self.manager.apply('eDP-1',self.video);self.manager.apply('HDMI-A-1',self.image)
        self.lwe.command.assert_not_called();self.lwe.start_command.assert_not_called()

    def test_hotplug_same_mode_uses_wildcard_over_stale_output(self):
        from mpvpaper_engine.models import OutputMode
        self.config.mode=OutputMode.SAME
        self.config.outputs={'*':{'wallpaper':str(self.video)},'HDMI-A-1':{'wallpaper':str(self.scene)}}
        self.manager.reconcile()
        self.assertEqual(self.manager.status('HDMI-A-1')['runtime'],'mpvpaper')
        self.lwe.start_command.assert_not_called()

    def test_disabled_wildcard_does_not_restore_stale_outputs(self):
        from mpvpaper_engine.models import OutputMode
        self.config.mode=OutputMode.SAME
        self.config.outputs={'*':{'wallpaper':str(self.video),'enabled':False},'eDP-1':{'wallpaper':str(self.image)}}
        self.assertEqual(self.manager.restore(),{})
        self.mpv.start.assert_not_called()
