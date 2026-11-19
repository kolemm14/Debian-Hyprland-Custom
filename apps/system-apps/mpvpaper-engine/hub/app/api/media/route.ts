const ALLOWED_EXTS = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"]);

export async function GET(request: Request) {
  const url = new URL(request.url);
  const filePath = url.searchParams.get("path");
  if (!filePath) {
    return new Response("Missing path", { status: 400 });
  }

  // Reject null bytes, carriage returns, or invalid control characters
  if (filePath.includes("\0") || filePath.includes("\r") || filePath.includes("\n")) {
    return new Response("Invalid path parameter", { status: 400 });
  }

  // Validate allowed extension
  const dotIndex = filePath.lastIndexOf(".");
  const ext = dotIndex !== -1 ? filePath.slice(dotIndex).toLowerCase() : "";
  if (!ALLOWED_EXTS.has(ext)) {
    return new Response("Invalid or disallowed media extension", { status: 403 });
  }

  // Reject directory traversal attempts and sensitive system paths upfront
  if (
    filePath.includes("..") ||
    filePath.startsWith("/etc") ||
    filePath.startsWith("/proc") ||
    filePath.startsWith("/sys") ||
    filePath.startsWith("/dev") ||
    filePath.startsWith("/root")
  ) {
    return new Response("Access denied: path traversal forbidden", { status: 403 });
  }

  const port = process.env.MPVPAPER_ENGINE_PORT || "48199";
  const targetUrl = `http://127.0.0.1:${port}/media?path=${encodeURIComponent(filePath)}`;

  try {
    const upstream = await fetch(targetUrl);
    if (!upstream.ok) {
      return new Response("Media not found or inaccessible", { status: upstream.status });
    }
    const contentType = upstream.headers.get("content-type") || "image/jpeg";
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch (err: any) {
    return new Response("Engine media service unavailable", { status: 503 });
  }
}
