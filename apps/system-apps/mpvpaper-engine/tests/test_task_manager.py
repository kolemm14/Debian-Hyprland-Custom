import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.task_manager import TaskManager, TaskRecord
from mpvpaper_engine.ipc import RPCError


def temporary_paths(root: Path) -> EnginePaths:
    return EnginePaths.from_environment({
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.paths = temporary_paths(self.base)
        self.paths.runtime_home.mkdir(parents=True, exist_ok=True)
        self.paths.cache_home.mkdir(parents=True, exist_ok=True)
        self.paths.temp_dir.mkdir(parents=True, exist_ok=True)
        self.tm = TaskManager(self.paths, max_workers=2)

        # Create a sample media file
        self.sample_file = self.base / "sample.png"
        self.sample_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)

    def tearDown(self):
        # Cancel any active tasks and allow worker threads to stop
        for task_id in list(self.tm.tasks):
            try:
                self.tm.cancel_task(task_id)
            except Exception:
                pass
        time.sleep(0.05)
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_estimate_validation(self):
        # Missing file
        with self.assertRaises(RPCError) as ctx:
            self.tm.estimate({"file_path": str(self.base / "missing.png")})
        self.assertEqual(ctx.exception.code, "file_not_found")

        # Missing file_path param
        with self.assertRaises(RPCError) as ctx:
            self.tm.estimate({})
        self.assertEqual(ctx.exception.code, "invalid_params")

        # Valid estimate
        res = self.tm.estimate({"file_path": str(self.sample_file), "media_type": "image"})
        self.assertIn("estimate", res)
        self.assertIn("target_resolution", res["estimate"])

    def test_start_optimize_requires_lossy_confirmation(self):
        with self.assertRaises(RPCError) as ctx:
            self.tm.start_optimize({
                "file_path": str(self.sample_file),
                "media_type": "image",
                "format": "webp",
                "confirmed_lossy": False,
            })
        self.assertEqual(ctx.exception.code, "confirmation_required")

    def test_start_optimize_success_and_cancel(self):
        res = self.tm.start_optimize({
            "file_path": str(self.sample_file),
            "media_type": "image",
            "format": "png",
            "resolution": "original",
            "compression": "weak",
            "confirmed_lossy": True,
        })
        self.assertIn("task_id", res)
        task_id = res["task_id"]

        status = self.tm.get_task(task_id)
        self.assertIn(status["state"], {"queued", "running", "completed"})

        cancelled = self.tm.cancel_task(task_id)
        self.assertIn(cancelled["state"], {"cancelled", "completed"})

    def test_task_not_found(self):
        with self.assertRaises(RPCError) as ctx:
            self.tm.get_task("nonexistent")
        self.assertEqual(ctx.exception.code, "task_not_found")
        with self.assertRaises(RPCError) as ctx:
            self.tm.cancel_task("nonexistent")
        self.assertEqual(ctx.exception.code, "task_not_found")

    def test_background_download_reports_bytes_and_cancels_stream(self):
        entered = threading.Event()
        closed = threading.Event()

        def worker(task):
            self.tm.update_download_progress(task.task_id, 128, 1024)
            self.tm.set_cancel_callback(task.task_id, closed.set)
            entered.set()
            task._cancel_event.wait(2)
            raise RuntimeError("download interrupted")

        started = self.tm.start_background("hub_download", worker)
        self.assertTrue(entered.wait(1))
        status = self.tm.get_task(started["task_id"])
        self.assertEqual(status["bytes_downloaded"], 128)
        self.assertEqual(status["total_bytes"], 1024)
        self.assertAlmostEqual(status["progress"], 0.125)
        cancelled = self.tm.cancel_task(started["task_id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertTrue(closed.wait(1))

    def test_background_task_cannot_be_cancelled_during_library_commit(self):
        entered = threading.Event()
        release = threading.Event()

        def worker(task):
            self.assertTrue(self.tm.begin_commit(task.task_id))
            entered.set()
            release.wait(1)
            return {"saved": True}

        started = self.tm.start_background("hub_download", worker)
        self.assertTrue(entered.wait(1))
        status = self.tm.cancel_task(started["task_id"])
        self.assertEqual(status["state"], "running")
        release.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            status = self.tm.get_task(started["task_id"])
            if status["state"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual(status["state"], "completed")

    def test_list_tasks(self):
        self.assertEqual(self.tm.list_tasks(), [])
        self.tm.start_optimize({
            "file_path": str(self.sample_file),
            "media_type": "image",
            "format": "png",
            "confirmed_lossy": True,
        })
        tasks = self.tm.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "media_optimize")


if __name__ == "__main__":
    unittest.main()
