#!/usr/bin/env python3
"""Opt-in GTK/IPC smoke test with isolated configuration and a synthetic project.

Usage: python3 tools/validate_runtime_gui.py /tmp/gui-report.json
No Scene renderer is launched. A temporary GUI window is shown for four seconds.
"""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mpvpaper_engine.gui import EngineWindow, Gtk, Adw, GLib
from mpvpaper_engine.gui_backend import GuiBackend
from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.config import load_config, save_config
from mpvpaper_engine.service import EngineService
from mpvpaper_engine.ipc import EngineClient
with tempfile.TemporaryDirectory(prefix='mpv-runtime-gui-') as tmp:
 root=Path(tmp)
 paths=EnginePaths.from_environment({'HOME':tmp,'XDG_CONFIG_HOME':str(root/'cfg'),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),'XDG_RUNTIME_DIR':str(root/'run')})
 config=load_config(paths);config.ui['hud']={'enabled':False};save_config(config,paths)
 scene=root/'synthetic-scene';scene.mkdir();(scene/'scene.pkg').touch();(scene/'project.json').write_text(json.dumps({'type':'scene','file':'scene.pkg'}))
 service=EngineService(paths);service.start()
 try:
  backend=GuiBackend(paths,client=EngineClient(paths),library_roots=(root/'library',))
  item=backend.import_project(scene)
  app=Adw.Application(application_id='io.github.mpvpaper.RuntimeSmoke')
  app.register()
  window=EngineWindow(app,backend);window.present();window.select(item)
  loop=GLib.MainLoop();GLib.timeout_add_seconds(4,lambda:(loop.quit(),False)[1]);loop.run()
  text=window.runtime_details.get_text()
  assert 'scene' in text and 'indisponible' in text,text
  result={'status':'PASS réel','scope':'GTK window construction, project registration and IPC diagnostic; no Scene rendering', 'diagnostic':text}
  Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/mpvpaper-runtime-gui-report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
  window.close()
 finally:
  service.shutdown()
print('GUI smoke PASS')
