/**
 * MPVpaper Hub ↔ MPVpaper Engine IPC Client (TypeScript / Node.js)
 *
 * Lightweight, secure Unix Domain Socket client communicating with the local
 * MPVpaper Engine daemon via JSON Lines protocol.
 */

import net from "node:net";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

export interface IpcError {
  code: string;
  message: string;
}

export interface IpcResponse<T = any> {
  id: number;
  ok: boolean;
  result?: T;
  error?: IpcError;
}

export const ALLOWED_IPC_METHODS = new Set([
  "engine.status",
  "engine_status",
  "engine.capabilities",
  "engine_capabilities",
  "media.estimate",
  "media_estimate",
  "media.optimize",
  "media_optimize",
  "task.status",
  "task_status",
  "task.cancel",
  "task_cancel",
  "task.list",
  "task_list",
  "ping",
  "play",
  "stop",
  "pause",
  "resume",
  "toggle_pause",
  "restart",
  "seek",
  "seek_relative",
  "set_volume",
  "set_mute",
  "set_speed",
  "set_loop",
  "set_fit",
  "set_color",
  "set_performance_profile",
  "get_state",
  "get_output_state",
  "list_outputs",
  "get_version",
  "configure_hud",
  "refresh_hud",
  "preview_hud",
  "clear_hud_preview",
  "save_playback_settings",
  "library.list",
  "library_list",
  "library.scan",
  "library_scan",
  "library.set_favorite",
  "library_set_favorite",
  "library.import",
  "library_import",
  "library.delete",
  "library_delete",
  "hub.import",
  "hub_import",
  "hub.v1.download",
  "hub.v1.download.start",
  "hub.v1.apply",
  "playlists.list",
  "playlists_list",
  "playlists.create",
  "playlists_create",
  "playlists.delete",
  "playlists_delete",
  "recommendations.list",
  "recommendations_list",
]);

export function getEngineSocketPath(): string {
  const runtimeDir =
    process.env.XDG_RUNTIME_DIR ||
    `/tmp/mpvpaper-engine-${process.getuid ? process.getuid() : 1000}`;
  return path.join(runtimeDir, "mpvpaper-engine", "engine.sock");
}

export class EngineIpcClient {
  private socketPath: string;
  private timeoutMs: number;
  private nextId = 1;

  constructor(socketPath?: string, timeoutMs: number = 3000) {
    this.socketPath = socketPath || getEngineSocketPath();
    this.timeoutMs = timeoutMs;
  }

  public isSocketAvailable(): boolean {
    try {
      if (!fs.existsSync(this.socketPath)) return false;
      const stat = fs.statSync(this.socketPath);
      return stat.isSocket();
    } catch {
      return false;
    }
  }

  public async request<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    if (!ALLOWED_IPC_METHODS.has(method)) {
      throw { code: "forbidden_method", message: `Méthode IPC non autorisée : ${method}` };
    }

    try {
      return await this.requestUnix<T>(method, params);
    } catch (err: any) {
      // A Unix timeout does not mean the RPC stopped. Retrying a mutating
      // operation over HTTP could download/apply the same wallpaper twice.
      if (err && (err._isApplicationError || err.code === "timeout")) {
        if (err._isApplicationError) delete err._isApplicationError;
        throw err;
      }
      try {
        return await this.requestHttp<T>(method, params);
      } catch (httpErr: any) {
        throw {
          code: "engine_unavailable",
          message: `Unix: ${err.message || err.code || err}; HTTP: ${httpErr.message || httpErr.code || httpErr}`,
        };
      }
    }
  }

  private async requestHttp<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    const port = process.env.MPVPAPER_ENGINE_PORT || "48199";
    const url = `http://127.0.0.1:${port}/rpc`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: this.nextId++, method, params }),
      });
      if (!res.ok) {
        throw { code: "http_error", message: `Erreur HTTP ${res.status} depuis Engine` };
      }
      const data: IpcResponse<T> = await res.json();
      if (!data.ok) {
        throw data.error || { code: "request_failed", message: "Échec de la requête Engine" };
      }
      return data.result as T;
    } catch (err: any) {
      if (err.code === "ECONNREFUSED" || (err.message && err.message.includes("fetch failed")) || (err.cause && err.cause.code === "ECONNREFUSED")) {
        throw { code: "engine_unavailable", message: "MPVpaper Engine n'est pas actif." };
      }
      throw err;
    }
  }

  private requestUnix<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    const requestId = this.nextId++;
    const payload = JSON.stringify({ id: requestId, method, params }) + "\n";

    return new Promise((resolve, reject) => {
      let resolved = false;
      let buffer = "";

      let socket: net.Socket;
      try {
        socket = net.createConnection({ path: this.socketPath });
      } catch (createErr) {
        return reject(createErr);
      }
      socket.setTimeout(this.timeoutMs);

      const cleanup = () => {
        socket.removeAllListeners();
        socket.destroy();
      };

      socket.on("connect", () => {
        socket.write(payload, "utf-8");
      });

      socket.on("data", (chunk) => {
        buffer += chunk.toString("utf-8");
        const newlineIndex = buffer.indexOf("\n");
        if (newlineIndex !== -1) {
          const line = buffer.slice(0, newlineIndex).trim();
          cleanup();
          resolved = true;
          try {
            const res: IpcResponse<T> = JSON.parse(line);
            if (!res.ok) {
              const rpcErr = (res.error || { code: "request_failed", message: "Échec de la requête Engine" }) as any;
              rpcErr._isApplicationError = true;
              reject(rpcErr);
            } else {
              resolve(res.result as T);
            }
          } catch (parseErr) {
            reject({ code: "invalid_json_response", message: "Réponse Engine invalide", _isApplicationError: true });
          }
        }
      });

      socket.on("timeout", () => {
        if (!resolved) {
          cleanup();
          reject({ code: "timeout", message: "Délai d'attente dépassé avec MPVpaper Engine" });
        }
      });

      socket.on("error", (err: any) => {
        if (!resolved) {
          cleanup();
          if (err.code === "ENOENT" || err.code === "ECONNREFUSED") {
            reject({ code: "engine_unavailable", message: "MPVpaper Engine n'est pas actif." });
          } else {
            reject(err);
          }
        }
      });
    });
  }

  public engineStatus(): Promise<any> {
    return this.request("engine.status");
  }

  public engineCapabilities(): Promise<any> {
    return this.request("engine.capabilities");
  }

  public mediaEstimate(params: Record<string, any>): Promise<any> {
    return this.request("media.estimate", params);
  }

  public mediaOptimize(params: Record<string, any>): Promise<any> {
    return this.request("media.optimize", params);
  }

  public taskStatus(taskId: string): Promise<any> {
    return this.request("task.status", { task_id: taskId });
  }

  public taskCancel(taskId: string): Promise<any> {
    return this.request("task.cancel", { task_id: taskId });
  }

  public taskList(limit = 20): Promise<any[]> {
    return this.request("task.list", { limit });
  }
}
