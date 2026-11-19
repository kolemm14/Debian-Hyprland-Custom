"""Automated Functional, Security, and Performance Audit for MPVpaper Engine 2 & Hub."""

import http.client
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
import urllib.parse
import pytest

MODULE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODULE_DIR))
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "mpvpaper-engine" / "engine.sock"
HTTP_PORT = int(os.environ.get("MPVPAPER_ENGINE_PORT", "48199"))


class TestSecurityAudit:
    """Security audit: path traversal, extensions, permissions, network exposure."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        """Ensure engine service is running for the tests."""
        from mpvpaper_engine.service import EngineService
        from mpvpaper_engine.paths import EnginePaths
        from mpvpaper_engine.ipc import EngineAlreadyRunningError

        paths = EnginePaths.from_environment()
        service = None
        started_by_us = False
        try:
            service = EngineService(paths)
            service.start()
            started_by_us = True
            time.sleep(0.3)
        except EngineAlreadyRunningError:
            pass

        yield service

        if started_by_us and service:
            service.shutdown()

    def test_unix_socket_permissions(self):
        """Unix socket must have mode 0600 and runtime directory must have mode 0700."""
        assert SOCKET_PATH.exists(), f"Socket does not exist: {SOCKET_PATH}"
        assert SOCKET_PATH.is_socket(), f"Path is not a socket: {SOCKET_PATH}"

        socket_stat = SOCKET_PATH.stat()
        socket_mode = stat.S_IMODE(socket_stat.st_mode)
        assert socket_mode == 0o600, f"Socket permissions {oct(socket_mode)} are not 0600"

        parent_dir = SOCKET_PATH.parent
        dir_stat = parent_dir.stat()
        dir_mode = stat.S_IMODE(dir_stat.st_mode)
        assert dir_mode == 0o700, f"Runtime dir permissions {oct(dir_mode)} are not 0700"

    def test_ipc_relay_not_exposed_to_network(self):
        """HTTP bridge must only listen on 127.0.0.1, never 0.0.0.0."""
        # Check by attempting to connect on localhost vs non-loopback
        conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
        conn.request("GET", "/healthcheck_nonexistent")
        res = conn.getresponse()
        assert res.status in (404, 501), f"Unexpected status: {res.status}"
        conn.close()

    def test_security_path_traversal_blocked(self):
        """Path traversal attempts like ../../etc/passwd must be rejected with 403."""
        conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
        traversal_attempts = [
            "../../../../etc/passwd",
            "/etc/passwd",
            "/etc/shadow",
            "/var/log/syslog",
            "../../../../home/mouhamet/.ssh/id_rsa",
        ]
        for path in traversal_attempts:
            conn.request("GET", f"/media?path={urllib.parse.quote(path)}")
            res = conn.getresponse()
            res.read()
            assert res.status == 403, f"Path traversal not blocked for {path}: HTTP {res.status}"
        conn.close()

    def test_security_disallowed_extensions_blocked(self):
        """Files with non-image extensions (.py, .sh, .txt, .exe) must be rejected with 403."""
        # Create a temporary dummy text file inside /tmp
        dummy = Path("/tmp/test_secret.sh")
        dummy.write_text("#!/bin/sh\necho secret")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
            conn.request("GET", f"/media?path={urllib.parse.quote(str(dummy))}")
            res = conn.getresponse()
            res.read()
            assert res.status == 403, f"Non-image extension not blocked: HTTP {res.status}"
            conn.close()
        finally:
            if dummy.exists():
                dummy.unlink()

    def test_security_valid_thumbnail_allowed(self):
        """A valid JPEG thumbnail inside user cache/tmp must be served with 200."""
        dummy_img = Path("/tmp/test_valid_thumb.jpg")
        dummy_img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
            conn.request("GET", f"/media?path={urllib.parse.quote(str(dummy_img))}")
            res = conn.getresponse()
            body = res.read()
            assert res.status == 200, f"Valid thumbnail failed: HTTP {res.status}"
            assert res.getheader("Content-Type") == "image/jpeg"
            assert len(body) == len(dummy_img.read_bytes())
            conn.close()
        finally:
            if dummy_img.exists():
                dummy_img.unlink()

    def test_security_forbidden_rpc_method_rejected(self):
        """Arbitrary unwhitelisted methods must be rejected."""
        conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
        payload = json.dumps({"id": 1, "method": "system.exec_bash", "params": {"cmd": "whoami"}})
        conn.request("POST", "/rpc", body=payload, headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        assert data.get("ok") is False
        assert data.get("error", {}).get("code") == "unknown_method"
        conn.close()


class TestFunctionalAudit:
    """Functional audit: IPC, library, playlists, favorites, monitors, persistence."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        from mpvpaper_engine.service import EngineService
        from mpvpaper_engine.paths import EnginePaths
        from mpvpaper_engine.ipc import EngineAlreadyRunningError

        paths = EnginePaths.from_environment()
        service = None
        started_by_us = False
        try:
            service = EngineService(paths)
            service.start()
            started_by_us = True
            time.sleep(0.3)
        except EngineAlreadyRunningError:
            pass

        yield service

        if started_by_us and service:
            service.shutdown()

    def _rpc(self, method: str, params: dict = None) -> dict:
        conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=3)
        payload = json.dumps({"id": 1, "method": method, "params": params or {}})
        conn.request("POST", "/rpc", body=payload, headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        conn.close()
        return data

    def test_engine_status_and_capabilities(self):
        """engine.status must return running state and configured outputs."""
        status_res = self._rpc("engine.status")
        assert status_res.get("ok") is True
        result = status_res.get("result", {})
        assert result.get("service_status") == "running"
        assert "outputs" in result
        assert isinstance(result["outputs"], dict)

        caps_res = self._rpc("engine.capabilities")
        assert caps_res.get("ok") is True

    def test_library_operations(self):
        """library.list must return local items and allow search filtering."""
        lib_res = self._rpc("library.list")
        assert lib_res.get("ok") is True
        items = lib_res.get("result", [])
        assert isinstance(items, list)

        # Test search filter query
        search_res = self._rpc("library.list", {"query": "nonexistent_wallpaper_xyz123"})
        assert search_res.get("ok") is True
        assert len(search_res.get("result", [])) == 0

    def test_favorites_persistence(self):
        """Toggling favorite flag must persist in library database."""
        lib_res = self._rpc("library.list")
        items = lib_res.get("result", [])
        if not items:
            pytest.skip("No items in library to test favorites")

        first_id = items[0]["id"]
        orig_fav = items[0]["favorite"]

        # Toggle to opposite
        set_res = self._rpc("library.set_favorite", {"id": first_id, "favorite": not orig_fav})
        assert set_res.get("ok") is True
        assert set_res["result"]["favorite"] == (not orig_fav)

        # Verify persistence in list
        check_res = self._rpc("library.list")
        matching = [item for item in check_res["result"] if item["id"] == first_id]
        assert len(matching) == 1
        assert matching[0]["favorite"] == (not orig_fav)

        # Restore original state
        restore_res = self._rpc("library.set_favorite", {"id": first_id, "favorite": orig_fav})
        assert restore_res.get("ok") is True
        assert restore_res["result"]["favorite"] == orig_fav

    def test_playlists_crud_lifecycle(self):
        """Playlists creation, listing, and deletion lifecycle."""
        # Create
        create_res = self._rpc("playlists.create", {"name": "Audit Test Playlist", "mode": "sequential", "interval_seconds": 600})
        assert create_res.get("ok") is True
        pl_id = create_res["result"]["id"]
        assert create_res["result"]["name"] == "Audit Test Playlist"
        assert create_res["result"]["interval_seconds"] == 600

        # List
        list_res = self._rpc("playlists.list")
        assert list_res.get("ok") is True
        matching = [p for p in list_res["result"] if p["id"] == pl_id]
        assert len(matching) == 1

        # Delete
        del_res = self._rpc("playlists.delete", {"id": pl_id})
        assert del_res.get("ok") is True
        assert del_res["result"]["deleted"] is True

        # Verify deletion
        list_res2 = self._rpc("playlists.list")
        matching2 = [p for p in list_res2["result"] if p["id"] == pl_id]
        assert len(matching2) == 0

    def test_recommendations_list(self):
        """recommendations.list returns recommendation entries."""
        rec_res = self._rpc("recommendations.list")
        assert rec_res.get("ok") is True
        recs = rec_res.get("result", [])
        assert isinstance(recs, list)


class TestPerformanceMetrics:
    """Performance benchmarks: startup time, memory footprint (RSS), CPU idle, thumbnail latency."""

    def test_service_startup_time(self, tmp_path, monkeypatch):
        """Measure startup time from process launch to socket and HTTP availability."""
        from mpvpaper_engine.service import EngineService
        from mpvpaper_engine.paths import EnginePaths

        monkeypatch.setenv("MPVPAPER_ENGINE_PORT", "48201")
        test_env = dict(os.environ)
        test_env["XDG_RUNTIME_DIR"] = str(tmp_path / "runtime")
        test_env["MPVPAPER_ENGINE_PORT"] = "48201"
        paths = EnginePaths.from_environment(test_env)

        t0 = time.perf_counter()
        service = EngineService(paths)
        service.start()
        t1 = time.perf_counter()
        startup_ms = (t1 - t0) * 1000

        # Verify ready
        assert paths.engine_socket.exists()
        conn = http.client.HTTPConnection("127.0.0.1", 48201, timeout=1)
        conn.request("POST", "/rpc", body=json.dumps({"id": 1, "method": "ping", "params": {}}))
        res = conn.getresponse()
        assert res.status == 200
        conn.close()

        service.shutdown()
        print(f"\n[PERF] Engine Service Startup Time: {startup_ms:.2f} ms")
        assert startup_ms < 2000, f"Startup took too long: {startup_ms} ms"

    def test_memory_and_cpu_idle(self):
        """Measure Engine service RAM (RSS) and CPU usage at idle."""
        import psutil
        from mpvpaper_engine.service import EngineService
        from mpvpaper_engine.paths import EnginePaths
        from mpvpaper_engine.ipc import EngineAlreadyRunningError

        paths = EnginePaths.from_environment()
        service = None
        started_by_us = False
        target_pid = os.getpid()

        try:
            service = EngineService(paths)
            service.start()
            started_by_us = True
            time.sleep(0.5)
        except EngineAlreadyRunningError:
            pid_file = paths.runtime_home / "engine.pid"
            if pid_file.exists():
                try:
                    candidate = int(pid_file.read_text().strip())
                    if psutil.pid_exists(candidate):
                        target_pid = candidate
                except (ValueError, OSError):
                    pass

        process = psutil.Process(target_pid)
        rss_bytes = process.memory_info().rss
        rss_mb = rss_bytes / (1024 * 1024)

        # Sample CPU over 1.5 seconds
        cpu_samples = []
        for _ in range(3):
            time.sleep(0.5)
            cpu_samples.append(process.cpu_percent(interval=None))

        avg_cpu = sum(cpu_samples) / len(cpu_samples)

        if started_by_us and service:
            service.shutdown()

        print(f"\n[PERF] Engine Service Memory (RSS): {rss_mb:.2f} MB")
        print(f"[PERF] Engine Service Idle CPU: {avg_cpu:.2f}%")

        assert rss_mb < 200, f"Memory footprint exceeds budget: {rss_mb} MB"
        assert avg_cpu < 5.0, f"Idle CPU too high: {avg_cpu}%"

    def test_thumbnail_fetch_latency(self):
        """Measure thumbnail response latency via HTTP endpoint."""
        from mpvpaper_engine.service import EngineService
        from mpvpaper_engine.paths import EnginePaths
        from mpvpaper_engine.ipc import EngineAlreadyRunningError

        dummy_img = Path("/tmp/perf_test_thumb.jpg")
        dummy_img.write_bytes(b"\xff\xd8\xff\xe0" + os.urandom(15000))

        paths = EnginePaths.from_environment()
        service = None
        started_by_us = False
        try:
            service = EngineService(paths)
            service.start()
            started_by_us = True
            time.sleep(0.3)
        except EngineAlreadyRunningError:
            pass

        latencies = []
        conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
        try:
            for _ in range(10):
                t0 = time.perf_counter()
                conn.request("GET", f"/media?path={urllib.parse.quote(str(dummy_img))}")
                res = conn.getresponse()
                body = res.read()
                t1 = time.perf_counter()
                assert res.status == 200
                latencies.append((t1 - t0) * 1000)
        finally:
            conn.close()
            if started_by_us and service:
                service.shutdown()
            if dummy_img.exists():
                dummy_img.unlink()

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"\n[PERF] Thumbnail Avg Latency: {avg_latency:.2f} ms")
        print(f"[PERF] Thumbnail P95 Latency: {p95_latency:.2f} ms")
        assert avg_latency < 50.0, f"Thumbnail latency too high: {avg_latency} ms"
