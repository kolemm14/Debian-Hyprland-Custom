import os
from pathlib import Path
import tempfile
import time
import unittest

from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.service import EngineService
from mpvpaper_engine.ipc import EngineClient, EngineServer, RPCError


def temporary_paths(root: Path) -> EnginePaths:
    return EnginePaths.from_environment({
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class TestIPCTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.paths = temporary_paths(self.base)
        self.paths.runtime_home.mkdir(parents=True, exist_ok=True)
        self.paths.cache_home.mkdir(parents=True, exist_ok=True)
        self.paths.temp_dir.mkdir(parents=True, exist_ok=True)

        self.service = EngineService(self.paths)
        self.service.server.start()
        self.client = EngineClient(self.paths)

        # Sample file
        self.sample = self.base / "sample_video.mp4"
        self.sample.write_bytes(b"\x00" * 1024)

    def tearDown(self):
        self.service.server.shutdown()
        time.sleep(0.05)
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_engine_status_and_capabilities(self):
        status = self.client.engine_status()
        self.assertIn("service_status", status)
        self.assertIn("active_tasks_count", status)

        caps = self.client.engine_capabilities()
        self.assertIn("media_optimizer", caps)
        self.assertEqual(caps["media_optimizer"]["default_initial_resolution"], "720p")
        self.assertEqual(caps["media_optimizer"]["default_initial_max_mb"], 150.0)
        self.assertIn("system_integration", caps)

    def test_rpc_handler_can_finish_after_initial_socket_read_timeout(self):
        def slow_handler(_params):
            time.sleep(2.2)
            return {"finished": True}

        self.service.server.methods["slow-test"] = slow_handler
        client = EngineClient(self.paths, timeout=3)
        self.assertEqual(client.request("slow-test"), {"finished": True})

    def test_media_estimate_and_optimize_ipc(self):
        est = self.client.media_estimate({
            "file_path": str(self.sample),
            "media_type": "video",
            "resolution": "720p",
        })
        self.assertIn("estimate", est)

        # Optimize without confirmation should raise error
        with self.assertRaises(Exception):
            self.client.media_optimize({
                "file_path": str(self.sample),
                "media_type": "video",
                "confirmed_lossy": False,
            })

        # With confirmation
        opt = self.client.media_optimize({
            "file_path": str(self.sample),
            "media_type": "video",
            "confirmed_lossy": True,
        })
        self.assertIn("task_id", opt)
        task_id = opt["task_id"]

        status = self.client.task_status(task_id)
        self.assertIn("state", status)
        self.assertEqual(status["id"], task_id)

        tasks = self.client.task_list()
        self.assertTrue(any(t["id"] == task_id for t in tasks))

        cancelled = self.client.task_cancel(task_id)
        self.assertIn(cancelled["state"], {"cancelled", "failed", "completed"})


if __name__ == "__main__":
    unittest.main()
