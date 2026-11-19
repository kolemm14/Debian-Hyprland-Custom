export type SearchWallpaper = {
  id: string;
  title: string;
  source: string;
  sourceUrl: string;
  author: string | null;
  authorRole: string | null;
  thumbnail: string;
  category: string;
  tags: string[];
  resolution: string | null;
  width: number | null;
  height: number | null;
  sizeMB: number | null;
  duration: number | null;
  type: "image";
  downloadUrl: null;
  downloadMode: "source";
  checkedAt: null;
  sourcePolicy: string;
  sourcePolicyUrl: string;
  previewUrl: null;
  engineDownloadUrl: string | null;
  publishedAt: string | null;
  external: true;
};

export type SourceStatus = {
  id: string;
  name: string;
  status: "available" | "rate_limited" | "unavailable" | "invalid_response";
  count: number;
};

type Provider = {
  id: string;
  name: string;
  minimumIntervalMs: number;
  search(query: string, fetcher: typeof fetch, signal?: AbortSignal): Promise<SearchWallpaper[]>;
};

const MAX_RESULTS = 12;
const MAX_RESPONSE_BYTES = 1_000_000;
const REQUEST_TIMEOUT_MS = 5_000;
const WALLHAVEN_HOSTS = new Set(["wallhaven.cc", "www.wallhaven.cc"]);
const NASA_HOST = "images-api.nasa.gov";
const NASA_ASSET_HOST = "images-assets.nasa.gov";
const SOURCE_CACHE_TTL_MS = 20_000;
const SOURCE_CACHE_MAX_ENTRIES = 64;
const sourceCache = new Map<string, { expiresAt: number; items: SearchWallpaper[] }>();
const sourceInFlight = new Map<string, Promise<SearchWallpaper[]>>();
const nextSourceRequestAt = new Map<string, number>();
const providerQueues = new Map<string, Promise<void>>();

function safeHttpsUrl(value: unknown, hosts: Set<string>): string | null {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || url.port || !hosts.has(url.hostname)) return null;
    return url.toString();
  } catch {
    return null;
  }
}

async function requestJson(url: URL, allowedHosts: Set<string>, fetcher: typeof fetch, signal?: AbortSignal): Promise<any> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetcher(url, {
      method: "GET",
      headers: { Accept: "application/json", "User-Agent": "MPVpaper-Hub/1.0" },
      signal: controller.signal,
      redirect: "follow",
    });
    let finalUrl: URL;
    try {
      finalUrl = new URL(response.url || url.toString());
    } catch {
      throw new Error("invalid_response");
    }
    if (finalUrl.protocol !== "https:" || !allowedHosts.has(finalUrl.hostname)) throw new Error("invalid_response");
    if (response.status === 429) throw new Error("rate_limited");
    if (!response.ok) throw new Error("unavailable");
    const declaredLength = Number(response.headers.get("content-length") || 0);
    if (declaredLength > MAX_RESPONSE_BYTES) throw new Error("invalid_response");
    if (!response.body) throw new Error("invalid_response");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let body = "";
    let bytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new Error("invalid_response");
      }
      body += decoder.decode(value, { stream: true });
    }
    body += decoder.decode();
    try {
      return JSON.parse(body);
    } catch {
      throw new Error("invalid_response");
    }
  } catch (error) {
    if (error instanceof Error && ["rate_limited", "unavailable", "invalid_response"].includes(error.message)) throw error;
    if (controller.signal.aborted) throw new Error("unavailable");
    throw new Error("unavailable");
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

function safeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}

function safeDate(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 40) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null;
}

function wallhavenCategory(value: unknown): string {
  if (value === "anime") return "Anime";
  if (value === "general") return "Autre";
  if (value === "people") return "Personnes";
  return "Autre";
}

async function searchWallhaven(query: string, fetcher: typeof fetch, signal?: AbortSignal): Promise<SearchWallpaper[]> {
  const url = new URL("https://wallhaven.cc/api/v1/search");
  url.searchParams.set("q", query);
  url.searchParams.set("categories", "111");
  url.searchParams.set("purity", "100");
  url.searchParams.set("sorting", "relevance");
  const payload = await requestJson(url, WALLHAVEN_HOSTS, fetcher, signal);
  if (!payload || !Array.isArray(payload.data)) throw new Error("invalid_response");
  const results: SearchWallpaper[] = [];
  for (const row of payload.data.slice(0, MAX_RESULTS)) {
    const id = typeof row?.id === "string" && /^[a-zA-Z0-9]{6}$/.test(row.id) ? row.id : null;
    const sourceUrl = id ? safeHttpsUrl(row.url, WALLHAVEN_HOSTS) : null;
    const thumbnail = safeHttpsUrl(row?.thumbs?.large, new Set(["th.wallhaven.cc"]));
    const path = safeHttpsUrl(row.path, new Set(["w.wallhaven.cc"]));
    if (!id || !sourceUrl || !thumbnail || !path || typeof row.resolution !== "string") continue;
    const width = safeInteger(row.dimension_x);
    const height = safeInteger(row.dimension_y);
    const bytes = safeInteger(row.file_size);
    results.push({
      id: `wallhaven:${id}`,
      // The search API omits a title; show the real source ID instead of inventing one.
      title: id,
      source: "Wallhaven",
      sourceUrl,
      author: typeof row.uploader?.username === "string" ? row.uploader.username.slice(0, 100) : null,
      authorRole: row.uploader?.username ? "uploader" : null,
      thumbnail,
      category: wallhavenCategory(row.category),
      tags: Array.isArray(row.tags) ? row.tags.slice(0, 20).flatMap((tag: any) => typeof tag?.name === "string" ? [tag.name.slice(0, 80)] : []) : [],
      resolution: width && height ? `${width}×${height}` : null,
      width,
      height,
      sizeMB: bytes ? Math.round((bytes / 1048576) * 100) / 100 : null,
      duration: null,
      type: "image",
      downloadUrl: null,
      downloadMode: "source",
      checkedAt: null,
      sourcePolicy: "Consulte la licence et les conditions sur la fiche originale avant utilisation.",
      sourcePolicyUrl: sourceUrl,
      previewUrl: null,
      engineDownloadUrl: path,
      publishedAt: safeDate(row.created_at),
      external: true,
    });
  }
  return results;
}

async function searchNasa(query: string, fetcher: typeof fetch, signal?: AbortSignal): Promise<SearchWallpaper[]> {
  const url = new URL("https://images-api.nasa.gov/search");
  url.searchParams.set("q", query);
  url.searchParams.set("media_type", "image");
  url.searchParams.set("page_size", String(MAX_RESULTS));
  const payload = await requestJson(url, new Set([NASA_HOST]), fetcher, signal);
  const rows = payload?.collection?.items;
  if (!Array.isArray(rows)) throw new Error("invalid_response");
  const results: SearchWallpaper[] = [];
  for (const row of rows.slice(0, MAX_RESULTS)) {
    const data = Array.isArray(row?.data) ? row.data[0] : null;
    const id = typeof data?.nasa_id === "string" && /^[a-zA-Z0-9_-]{1,100}$/.test(data.nasa_id) ? data.nasa_id : null;
    const preview = Array.isArray(row?.links) ? row.links.find((link: any) => link?.rel === "preview" && link?.render === "image") : null;
    const thumbnail = safeHttpsUrl(preview?.href, new Set([NASA_ASSET_HOST]));
    if (!id || !thumbnail || data.media_type !== "image") continue;
    const title = typeof data.title === "string" && data.title.trim() ? data.title.trim().slice(0, 240) : id;
    const keywords = Array.isArray(data.keywords) ? data.keywords.slice(0, 20).flatMap((tag: unknown) => typeof tag === "string" ? [tag.slice(0, 80)] : []) : [];
    const sourceUrl = `https://images.nasa.gov/details/${encodeURIComponent(id)}`;
    results.push({
      id: `nasa:${id}`,
      title,
      source: "NASA Images",
      sourceUrl,
      author: typeof data.photographer === "string" ? data.photographer.slice(0, 100) : null,
      authorRole: typeof data.photographer === "string" ? "publisher" : null,
      thumbnail,
      category: "Autre",
      tags: keywords,
      resolution: null,
      width: null,
      height: null,
      sizeMB: null,
      duration: null,
      type: "image",
      downloadUrl: null,
      downloadMode: "source",
      checkedAt: null,
      sourcePolicy: "Vérifiez les droits et crédits associés à cette ressource sur la fiche NASA originale.",
      sourcePolicyUrl: sourceUrl,
      previewUrl: null,
      // NASA preview assets are public images and can be imported locally.
      engineDownloadUrl: thumbnail,
      publishedAt: safeDate(data.date_created),
      external: true,
    });
  }
  return results;
}

const providers: Provider[] = [
  { id: "wallhaven", name: "Wallhaven", minimumIntervalMs: 1400, search: searchWallhaven },
  { id: "nasa", name: "NASA Images", minimumIntervalMs: 500, search: searchNasa },
];

function awaitOrAbort<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise;
  if (signal.aborted) return Promise.reject(new DOMException("Aborted", "AbortError"));
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
  });
}

async function waitOrAbort(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return;
  }
  await awaitOrAbort(new Promise<void>((resolve) => setTimeout(resolve, ms)), signal);
}

async function searchQueued(provider: Provider, query: string, fetcher: typeof fetch, signal?: AbortSignal) {
  const previous = providerQueues.get(provider.id) || Promise.resolve();
  let release!: () => void;
  const turn = new Promise<void>((resolve) => { release = resolve; });
  providerQueues.set(provider.id, turn);
  try {
    await awaitOrAbort(previous, signal);
    const wait = Math.max(0, (nextSourceRequestAt.get(provider.id) || 0) - Date.now());
    await waitOrAbort(wait, signal);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    nextSourceRequestAt.set(provider.id, Date.now() + provider.minimumIntervalMs);
    return await provider.search(query, fetcher, signal);
  } finally {
    release();
    if (providerQueues.get(provider.id) === turn) providerQueues.delete(provider.id);
  }
}

async function searchProvider(provider: Provider, query: string, fetcher: typeof fetch, signal?: AbortSignal) {
  const key = `${provider.id}:${query.trim().toLocaleLowerCase("fr")}`;
  const cached = sourceCache.get(key);
  if (cached && cached.expiresAt > Date.now()) return cached.items;
  if (cached) sourceCache.delete(key);
  const pending = sourceInFlight.get(key);
  if (pending) return pending;
  const request = searchQueued(provider, query, fetcher, signal).then((items) => {
    sourceCache.set(key, { expiresAt: Date.now() + SOURCE_CACHE_TTL_MS, items });
    if (sourceCache.size > SOURCE_CACHE_MAX_ENTRIES) {
      const oldest = sourceCache.keys().next().value;
      if (oldest) sourceCache.delete(oldest);
    }
    return items;
  }).finally(() => sourceInFlight.delete(key));
  sourceInFlight.set(key, request);
  return request;
}

export async function searchExternalWallpapers(query: string, fetcher: typeof fetch = fetch, signal?: AbortSignal) {
  const settled = await Promise.all(providers.map(async (provider) => {
    try {
      const items = await searchProvider(provider, query, fetcher, signal);
      return { provider, items, status: "available" as const };
    } catch (error) {
      const code = error instanceof Error ? error.message : "unavailable";
      const status = code === "rate_limited" ? "rate_limited" as const : code === "invalid_response" ? "invalid_response" as const : "unavailable" as const;
      return { provider, items: [] as SearchWallpaper[], status };
    }
  }));
  const seen = new Set<string>();
  const items: SearchWallpaper[] = [];
  for (const result of settled) {
    for (const item of result.items) {
      const key = item.sourceUrl.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(item);
    }
  }
  const sources: SourceStatus[] = settled.map(({ provider, items: sourceItems, status }) => ({
    id: provider.id,
    name: provider.name,
    status,
    count: sourceItems.length,
  }));
  return { items, sources };
}
