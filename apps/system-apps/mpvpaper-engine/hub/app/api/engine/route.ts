import { EngineIpcClient, ALLOWED_IPC_METHODS } from "@/lib/engine-ipc-client";

export async function POST(request: Request) {
  try {
    const origin = request.headers.get("origin");
    if (origin && origin !== new URL(request.url).origin) {
      return Response.json(
        { ok: false, error: { code: "origin_rejected", message: "Origine non autorisée" } },
        { status: 403 }
      );
    }
    const body = await request.json().catch(() => null);
    if (!body || typeof body !== "object") {
      return Response.json(
        { ok: false, error: { code: "invalid_request", message: "Corps de requête invalide" } },
        { status: 400 }
      );
    }

    const { method, params } = body as { method?: string; params?: Record<string, any> };
    if (!method || typeof method !== "string" || !ALLOWED_IPC_METHODS.has(method)) {
      return Response.json(
        { ok: false, error: { code: "invalid_method", message: `Méthode non autorisée : ${method}` } },
        { status: 400 }
      );
    }

    const timeout = method === "hub.v1.download" ? 300_000
      : method === "library.import" || method === "library_import" ? 120_000
      : method === "library.scan" || method === "library_scan" ? 90_000
      : 3_000;
    const client = new EngineIpcClient(undefined, timeout);
    try {
      const result = await client.request(method, params || {});
      return Response.json({ ok: true, result });
    } catch (ipcErr: any) {
      const statusCode = ipcErr.code === "engine_unavailable" ? 503 : 400;
      return Response.json(
        {
          ok: false,
          error: {
            code: ipcErr.code || "engine_error",
            message: ipcErr.message || "Erreur lors de la communication avec Engine",
          },
        },
        { status: statusCode }
      );
    }
  } catch (err: any) {
    return Response.json(
      { ok: false, error: { code: "internal_error", message: err.message || "Erreur interne" } },
      { status: 500 }
    );
  }
}
