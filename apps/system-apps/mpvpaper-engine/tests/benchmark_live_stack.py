"""Benchmark live stack: starts Engine & Hub, measures memory, CPU, latencies, and stops cleanly."""

import http.client
import json
import os
import subprocess
import time
import urllib.parse
import psutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DEV_SCRIPT = os.path.join(ENGINE_ROOT, "scripts", "dev.sh")
STOP_SCRIPT = os.path.join(ENGINE_ROOT, "scripts", "stop.sh")

print("=== Starting live Engine + Hub stack ===")
t0 = time.perf_counter()
dev_proc = subprocess.Popen([DEV_SCRIPT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=os.setsid)

# Wait for both Engine (48199) and Hub (5173) to be reachable
engine_ready = False
hub_ready = False
deadline = time.time() + 45

while time.time() < deadline:
    if not engine_ready:
        try:
            c = http.client.HTTPConnection("127.0.0.1", 48199, timeout=1)
            c.request("POST", "/rpc", body=json.dumps({"id": 1, "method": "ping", "params": {}}), headers={"Content-Type": "application/json"})
            res = c.getresponse()
            if res.status == 200:
                engine_ready = True
                t_engine = time.perf_counter() - t0
                print(f"[*] Engine ready in {t_engine*1000:.1f} ms")
            c.close()
        except Exception:
            pass

    if not hub_ready:
        try:
            c = http.client.HTTPConnection("127.0.0.1", 5173, timeout=1)
            c.request("HEAD", "/")
            res = c.getresponse()
            if res.status == 200:
                hub_ready = True
                t_hub = time.perf_counter() - t0
                print(f"[*] Hub ready in {t_hub*1000:.1f} ms")
            c.close()
        except Exception:
            pass

    if engine_ready and hub_ready:
        break
    time.sleep(0.5)

print(f"Stack startup complete: engine_ready={engine_ready}, hub_ready={hub_ready}")

# Identify processes
engine_pids = []
hub_pids = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info['cmdline'] or [])
        if "mpvpaper-engine-service.py" in cmd:
            engine_pids.append(p)
        elif "run-framework.mjs" in cmd or "workerd" in cmd or ("vite" in cmd and "mpvpaper" in cmd):
            hub_pids.append(p)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print(f"Detected Engine PIDs: {[p.pid for p in engine_pids]}")
print(f"Detected Hub PIDs: {[p.pid for p in hub_pids]}")

# Memory measurement (RSS)
engine_rss = sum(p.memory_info().rss for p in engine_pids) / (1024 * 1024)
hub_rss = sum(p.memory_info().rss for p in hub_pids) / (1024 * 1024)
total_rss = engine_rss + hub_rss

print(f"\n--- MEMORY (RSS) AT IDLE ---")
print(f"Engine Service RAM: {engine_rss:.2f} MB")
print(f"Hub (Node + Workerd) RAM: {hub_rss:.2f} MB")
print(f"Total Stack RAM: {total_rss:.2f} MB")

# CPU measurement over 3 seconds
time.sleep(1)
cpu_samples_engine = []
cpu_samples_hub = []
for _ in range(3):
    time.sleep(1)
    e_cpu = sum(p.cpu_percent(interval=None) for p in engine_pids if p.is_running())
    h_cpu = sum(p.cpu_percent(interval=None) for p in hub_pids if p.is_running())
    cpu_samples_engine.append(e_cpu)
    cpu_samples_hub.append(h_cpu)

avg_e_cpu = sum(cpu_samples_engine) / len(cpu_samples_engine)
avg_h_cpu = sum(cpu_samples_hub) / len(cpu_samples_hub)
print(f"\n--- CPU USAGE AT IDLE ---")
print(f"Engine Service Idle CPU: {avg_e_cpu:.2f}%")
print(f"Hub Frontend Idle CPU: {avg_h_cpu:.2f}%")

# Latencies
print(f"\n--- LATENCY MEASUREMENTS ---")
# 1. Hub -> Engine RPC via /api/engine
lat_rpc = []
for _ in range(5):
    t_start = time.perf_counter()
    conn = http.client.HTTPConnection("127.0.0.1", 5173, timeout=3)
    conn.request("POST", "/api/engine", body=json.dumps({"method": "engine.status", "params": {}}), headers={"Content-Type": "application/json"})
    res = conn.getresponse()
    res.read()
    lat_rpc.append((time.perf_counter() - t_start) * 1000)
    conn.close()

avg_rpc_lat = sum(lat_rpc) / len(lat_rpc)
print(f"/api/engine RPC Latency (avg 5 requests): {avg_rpc_lat:.2f} ms")

# 2. Thumbnail delivery via /api/media
dummy_thumb = "/tmp/benchmark_thumb.jpg"
with open(dummy_thumb, "wb") as f:
    f.write(b"\xff\xd8\xff\xe0" + os.urandom(25000))

lat_media = []
try:
    for _ in range(5):
        t_start = time.perf_counter()
        conn = http.client.HTTPConnection("127.0.0.1", 5173, timeout=3)
        conn.request("GET", f"/api/media?path={urllib.parse.quote(dummy_thumb)}")
        res = conn.getresponse()
        res.read()
        lat_media.append((time.perf_counter() - t_start) * 1000)
        conn.close()
    avg_media_lat = sum(lat_media) / len(lat_media)
    print(f"/api/media Thumbnail Latency (avg 5 requests): {avg_media_lat:.2f} ms")
finally:
    if os.path.exists(dummy_thumb):
        os.unlink(dummy_thumb)

print("\n=== Stopping live stack ===")
subprocess.run([STOP_SCRIPT], check=True)
try:
    os.killpg(os.getpgid(dev_proc.pid), 15)
except Exception:
    pass
time.sleep(1)
print("Stack stopped cleanly.")
