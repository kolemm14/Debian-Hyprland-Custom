import { spawn } from "node:child_process";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const [portText, persistText] = process.argv.slice(2);

const hubRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wrangler = path.join(hubRoot, "node_modules/wrangler/bin/wrangler.js");
const config = path.join(hubRoot, "dist/server/wrangler.json");
const enginePort = Number(process.env.MPVPAPER_ENGINE_PORT || 48199);
async function availablePort() {
  return await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      probe.close((error) => error ? reject(error) : resolve(address.port));
    });
  });
}
const port = portText ? Number(portText) : Number(process.env.MPVPAPER_HUB_PORT || await availablePort());
const persistDir = persistText || process.env.MPVPAPER_HUB_STATE_DIR || path.join(
  process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"), "mpvpaper-engine/hub-state",
);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("Usage: local-hub-server.mjs [loopback-port] [persist-dir]");
}
const workerPort = await new Promise((resolve, reject) => {
  const probe = net.createServer();
  probe.once("error", reject);
  probe.listen(0, "127.0.0.1", () => {
    const address = probe.address();
    probe.close((error) => error ? reject(error) : resolve(address.port));
  });
});

const worker = spawn(process.execPath, [
  "--import", "./scripts/sites-env.mjs", wrangler, "dev", "--config", config,
  "--local", "--persist-to", persistDir, "--ip", "127.0.0.1",
  "--port", String(workerPort), "--inspector-port", "0",
], { cwd: hubRoot, env: process.env, stdio: "inherit" });

let stopping = false;
let server;
const stop = (signal = "SIGTERM") => {
  if (stopping) return;
  stopping = true;
  worker.kill(signal);
  server?.close();
};
process.once("SIGTERM", () => stop());
process.once("SIGINT", () => stop("SIGINT"));
worker.once("exit", (code, signal) => {
  if (!stopping) process.exitCode = typeof code === "number" ? code : (signal ? 1 : 0);
  stop();
});

let ready = false;
for (let attempt = 0; attempt < 120 && !stopping; attempt++) {
  try {
    await new Promise((resolve, reject) => {
      const request = http.get({ hostname: "127.0.0.1", port: workerPort, path: "/", timeout: 500 }, (response) => {
        response.resume();
        response.once("end", resolve);
      });
      request.once("error", reject);
      request.once("timeout", () => request.destroy(new Error("Hub worker readiness timeout")));
    });
    ready = true;
    break;
  } catch {
    await delay(250);
  }
}
if (!ready || stopping) {
  stop();
  throw new Error("MPVpaper Hub worker did not become ready");
}

function proxy(req, res, targetPort, targetPath = req.url) {
  const upstream = http.request({
    hostname: "127.0.0.1", port: targetPort, path: targetPath,
    method: req.method, headers: { ...req.headers, host: `127.0.0.1:${targetPort}` },
  }, (response) => {
    res.writeHead(response.statusCode || 502, response.headers);
    response.pipe(res);
  });
  upstream.once("error", (error) => {
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: { code: "hub_proxy_error", message: error.message } }));
  });
  req.pipe(upstream);
}

server = http.createServer((req, res) => {
  const pathname = new URL(req.url || "/", "http://127.0.0.1");
  if (pathname.pathname === "/api/engine" && req.method === "POST") {
    proxy(req, res, enginePort, "/rpc");
    return;
  }
  if (pathname.pathname === "/api/media" && req.method === "GET") {
    proxy(req, res, enginePort, `/media${pathname.search}`);
    return;
  }
  proxy(req, res, workerPort);
});
server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`MPVpaper Hub prêt sur http://127.0.0.1:${port}/\n`);
});
