"use client";

import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import {
  Search, Heart, Download, ExternalLink, Play, SlidersHorizontal, Monitor,
  Sparkles, Star, Info, Compass, Globe, Check, X, Film, Leaf, LoaderCircle,
  Lock, Moon, Layers, Sliders, ListMusic, History, ShieldAlert, Maximize2,
  RotateCw, Settings, AlertTriangle, Eye, ArrowRight, ShieldCheck, CheckCircle2,
  Pause, Square, Volume2, VolumeX, Trash2, Plus, FolderOpen, Image, Video,
  ChevronRight, LayoutGrid
} from "lucide-react";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import type { Wallpaper } from "@/lib/hub";
import { EngineConnection } from "@/components/engine-connection";
import { mixRecommendations, recommendationSummary, type EngineProfile } from "@/lib/recommendations";
import {
  type LocalMediaItem, type Playlist, type HistoryEntry, type WebProject,
  type MonitorConfig, type LockscreenConfig, type ScreensaverConfig,
  type VideoOptimizerParams, type ImageOptimizerParams,
  DEFAULT_LOCAL_LIBRARY, DEFAULT_MONITORS, DEFAULT_WEB_PROJECTS,
  INITIAL_OPTIMIZER_VIDEO, INITIAL_OPTIMIZER_IMAGE,
  estimateVideoOptimization, estimateImageOptimization
} from "@/lib/local-hub";

/* ────────────────── Types ────────────────── */

type Item = Wallpaper & {
  favorites: number; votes: number; average: number | null; downloads: number;
  views: number; weekly: number; score: number | null; favorite: boolean; rating: number | null;
  external?: boolean; engineDownloadUrl?: string | null; publishedAt?: string | null;
};

type NavSection =
  | "library" | "live" | "images" | "scenes"
  | "discover" | "favorites" | "playlists" | "recent"
  | "monitors" | "settings" | "hud";

type SelectedMedia = {
  type: "catalog" | "local";
  catalogItem?: Item;
  localItem?: LibraryItem;
};

type LibraryItem = {
  id: number;
  path: string;
  title: string;
  type: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  video_codec: string | null;
  file_size: number;
  thumbnail_path: string | null;
  source: string;
  favorite: boolean;
  date_added: string;
  missing: boolean;
};

/* ────────────────── Helpers ────────────────── */

const SOURCE_COLORS: Record<string, string> = {
  "YouTube": "#ff4242",
  "MotionBGS": "#b89aff", "LivelyWallpaper.app": "#5cdbcb", "MyLiveWallpapers": "#f29bbc",
  "MoeWalls": "#ffc87a", "Wallsflow": "#99b7ff", "Backiee": "#ff9b79", "VSThemes": "#b4baff",
  "Steam Workshop": "#79b3d4",
};

const CATEGORIES = ["Tous", "Anime", "Jeux", "Nature", "Ville", "Espace"];
const HUB_ENGINE_SYNC_KEY = "mpvpaper-hub-engine-sync-v1";
const DISCOVER_MODES = [
  ["explore", "Explorer"], ["trending", "Tendances"],
  ["newest", "Nouveautés"], ["rated", "Les mieux notés"],
] as const;

function fmtSize(bytes: number): string {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} Mo` : `${(bytes / 1024).toFixed(0)} Ko`;
}

function fmtRes(w: number | null, h: number | null): string {
  if (!w || !h) return "—";
  if (w >= 3840) return "4K";
  if (w >= 2560) return "1440p";
  if (w >= 1920) return "1080p";
  if (w >= 1280) return "720p";
  return `${w}×${h}`;
}

function fmtDuration(s: number | null): string {
  if (!s) return "";
  const m = Math.floor(s / 60); const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function Thumb({ item, className = "" }: { item: { thumbnail?: string; thumbnail_path?: string | null; title: string; source?: string }; className?: string }) {
  const [failed, setFailed] = useState(false);
  const src = item.thumbnail || (item.thumbnail_path ? `/api/media?path=${encodeURIComponent(item.thumbnail_path)}` : null);
  return src && !failed ? (
    <img className={className} src={src} alt={item.title} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  ) : (
    <div className={"image-fallback " + className}><Film size={32} /><span>{item.source || "Média"}</span></div>
  );
}

async function engineRPC(method: string, params: Record<string, any> = {}): Promise<any> {
  const res = await fetch("/api/engine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, params }),
  });
  const data = (await res.json()) as any;
  if (res.ok && data?.ok) return data.result;
  throw new Error(data?.error?.message || "Erreur Engine");
}

/* ────────────────── Main Component ────────────────── */

export default function Hub() {
  const [embedded, setEmbedded] = useState(false);
  /* ── Navigation ── */
  const [section, setSection] = useState<NavSection>("library");

  /* ── Engine Connection ── */
  const [engineConnected, setEngineConnected] = useState<boolean | null>(null);
  const [engineInfo, setEngineInfo] = useState<any>(null);
  const [outputs, setOutputs] = useState<string[]>([]);
  const [selectedOutput, setSelectedOutput] = useState("*");

  /* ── Selection State (unified) ── */
  const [selectedMedia, setSelectedMedia] = useState<SelectedMedia | null>(null);

  /* ── Library (real data from Engine) ── */
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryQuery, setLibraryQuery] = useState("");
  const libraryLoaded = useRef(false);

  /* ── Catalog (Discover) ── */
  const [catalogItems, setCatalogItems] = useState<Item[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const catalogLoaded = useRef(false);
  const [catalogQuery, setCatalogQuery] = useState("");
  const [searchItems, setSearchItems] = useState<Item[]>([]);
  const [searchSources, setSearchSources] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [downloadedCatalog, setDownloadedCatalog] = useState<Record<string, number>>({});
  const [downloadBusyId, setDownloadBusyId] = useState<string | null>(null);
  const [downloadBusyTitle, setDownloadBusyTitle] = useState("");
  const [downloadTaskId, setDownloadTaskId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{ downloaded: number; total: number }>({ downloaded: 0, total: 0 });
  const [downloadPhase, setDownloadPhase] = useState("Préparation du téléchargement…");
  const [downloadCanceling, setDownloadCanceling] = useState(false);
  const [favoriteCatalog, setFavoriteCatalog] = useState<Record<string, boolean>>({});
  const [engineSyncReady, setEngineSyncReady] = useState(false);
  const [catalogSource, setCatalogSource] = useState("Toutes les sources");
  const [catalogCategory, setCatalogCategory] = useState("Tous");
  const [discoverMode, setDiscoverMode] = useState<(typeof DISCOVER_MODES)[number][0]>("explore");
  const [signedIn, setSignedIn] = useState(false);

  /* ── Playlists ── */
  const [playlists, setPlaylists] = useState<any[]>([]);
  const [newPlaylistName, setNewPlaylistName] = useState("");

  /* ── History ── */
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  /* ── Recommendations ── */
  const [recommendations, setRecommendations] = useState<any[]>([]);

  /* ── Playback state ── */
  const [playbackBusy, setPlaybackBusy] = useState(false);
  const [catalogPreviewPlaying, setCatalogPreviewPlaying] = useState(false);
  const [playbackControls, setPlaybackControls] = useState<any>(null);
  const [localImportPath, setLocalImportPath] = useState("");
  const [localImportBusy, setLocalImportBusy] = useState(false);
  const volumeDebounce = useRef<number | null>(null);
  const speedDebounce = useRef<number | null>(null);
  useEffect(() => setCatalogPreviewPlaying(false), [selectedMedia?.catalogItem?.id]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(HUB_ENGINE_SYNC_KEY);
      const value = raw ? JSON.parse(raw) : null;
      if (value && typeof value === "object") {
        const downloaded = Object.fromEntries(Object.entries(value.downloaded || {}).filter((entry): entry is [string, number] =>
          typeof entry[0] === "string" && Number.isSafeInteger(entry[1]) && Number(entry[1]) > 0
        ));
        const favorites = Object.fromEntries(Object.entries(value.favorites || {}).filter((entry): entry is [string, boolean] =>
          typeof entry[0] === "string" && typeof entry[1] === "boolean"
        ));
        setDownloadedCatalog(downloaded);
        setFavoriteCatalog(favorites);
      }
    } catch {
      // Private or full WebKit storage should not prevent browsing.
    } finally {
      setEngineSyncReady(true);
    }
  }, []);

  useEffect(() => {
    if (!engineSyncReady) return;
    try {
      localStorage.setItem(HUB_ENGINE_SYNC_KEY, JSON.stringify({
        downloaded: downloadedCatalog,
        favorites: favoriteCatalog,
      }));
    } catch {
      // Engine remains usable even when the WebKit storage quota is unavailable.
    }
  }, [engineSyncReady, downloadedCatalog, favoriteCatalog]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("embedded") === "engine") {
      setEmbedded(true);
      setSection("discover");
    }
  }, []);

  /* ── Engine Profile (for recommendations mixing) ── */
  const [engineProfile, setEngineProfile] = useState<EngineProfile | null>(null);

  /* ───────── Engine Status Check ───────── */
  const checkEngine = useCallback(async () => {
    try {
      const result = await engineRPC("engine.status");
      setEngineConnected(true);
      setEngineInfo((previous: any) => JSON.stringify(previous) === JSON.stringify(result) ? previous : result);
    } catch {
      setEngineConnected(false);
      setEngineInfo(null);
    }
  }, []);

  useEffect(() => {
    void checkEngine();
    const t = setInterval(() => {
      if (document.visibilityState === "visible") void checkEngine();
    // The embedded Hub can open while the Engine service is still starting.
    // Retry quickly until it connects so actions do not stay disabled for 30s.
    }, engineConnected ? 30000 : 1500);
    return () => clearInterval(t);
  }, [checkEngine, engineConnected]);

  /* ───────── Load outputs ───────── */
  useEffect(() => {
    if (!engineConnected) return;
    engineRPC("list_outputs").then(o => {
      if (Array.isArray(o) && o.length > 0) {
        setOutputs(o);
        setSelectedOutput(o[0]);
      }
    }).catch(() => {});
  }, [engineConnected]);

  /* ───────── Load Library from Engine ───────── */
  const loadLibrary = useCallback(async (scan = false) => {
    setLibraryLoading(true);
    try {
      if (scan) await engineRPC("library.scan", {});
      const items = await engineRPC("library.list", { query: "" });
      setLibraryItems(Array.isArray(items) ? items : []);
    } catch {
      // Fallback: try list without scan
      try {
        const items = await engineRPC("library.list", { query: "" });
        setLibraryItems(Array.isArray(items) ? items : []);
      } catch {
        setLibraryItems([]);
      }
    } finally {
      libraryLoaded.current = true;
      setLibraryLoading(false);
    }
  }, []);

  useEffect(() => {
    const usesLibrary = ["library", "favorites", "live", "images", "scenes"].includes(section);
    if (engineConnected && usesLibrary && !libraryLoaded.current) {
      void loadLibrary(true);
    }
  }, [engineConnected, section, loadLibrary]);

  /* ───────── Load Catalog ───────── */
  useEffect(() => {
    if (section !== "discover" || catalogLoaded.current) return;
    catalogLoaded.current = true;
    setCatalogLoading(true);
    fetch("/api/catalog").then(r => {
      if (!r.ok) throw new Error("Catalogue Hub indisponible");
      return r.json();
    }).then((data: any) => {
      setCatalogItems(data.items || []);
      setSignedIn(data.signedIn || false);
    }).catch(() => { catalogLoaded.current = false; }).finally(() => setCatalogLoading(false));
  }, [section]);

  useEffect(() => {
    const query = catalogQuery.trim();
    if (query.length < 2) {
      setSearchItems([]);
      setSearchSources([]);
      setSearchLoading(false);
      return;
    }
    const controller = new AbortController();
    setSearchLoading(true);
    setSearchSources([]);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Recherche externe indisponible");
        const data: any = await response.json();
        if (controller.signal.aborted) return;
        const items: Item[] = (Array.isArray(data.items) ? data.items : []).map((item: any) => ({
          ...item, favorites: item.favorites || 0, votes: item.votes || 0,
          average: item.average ?? null, downloads: item.downloads || 0,
          views: item.views || 0, weekly: item.weekly || 0, score: item.score ?? null,
          favorite: false, rating: null,
        }));
        setSearchItems(items);
        setSearchSources(Array.isArray(data.sources) ? data.sources : []);
      } catch {
        if (!controller.signal.aborted) {
          setSearchItems([]);
          setSearchSources([{ id: "search", name: "Recherche multi-sources", status: "unavailable", count: 0 }]);
        }
      } finally {
        if (!controller.signal.aborted) setSearchLoading(false);
      }
    }, 300);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [catalogQuery]);

  /* ───────── Load Playlists ───────── */
  useEffect(() => {
    if (engineConnected && section === "playlists") {
      engineRPC("playlists.list").then(p => setPlaylists(Array.isArray(p) ? p : [])).catch(() => {});
    }
  }, [engineConnected, section]);

  /* ───────── Load Recommendations ───────── */
  useEffect(() => {
    if (engineConnected && !embedded && section === "discover") {
      engineRPC("recommendations.list", { limit: 16 }).then(r => setRecommendations(Array.isArray(r) ? r : [])).catch(() => {});
    }
  }, [engineConnected, embedded, section]);

  /* ───────── Filtered Items ───────── */
  const filteredLibrary = useMemo(() => {
    let items = libraryItems;
    if (section === "live") items = items.filter(i => i.type === "video");
    else if (section === "images") items = items.filter(i => i.type === "image");
    else if (section === "scenes") items = items.filter(i => i.type === "scene");
    else if (section === "favorites") items = items.filter(i => i.favorite);
    if (libraryQuery) {
      const q = libraryQuery.toLowerCase();
      items = items.filter(i => i.title.toLowerCase().includes(q) || i.path.toLowerCase().includes(q));
    }
    return items;
  }, [libraryItems, section, libraryQuery]);

  const filteredCatalog = useMemo(() => {
    const q = catalogQuery.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const pool = catalogQuery.trim().length >= 2
      ? [...catalogItems.filter(w =>
          [w.title, w.source, ...w.tags].join(" ").toLowerCase().normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "").includes(q)
        ), ...searchItems]
      : catalogItems;
    const unique = new Map(pool.map(item => [item.id, item]));
    const filtered = [...unique.values()].filter(w =>
      (catalogCategory === "Tous" || w.category === catalogCategory) &&
      (catalogSource === "Toutes les sources" || w.source === catalogSource) &&
      (w.external || [w.title, w.source, ...w.tags].join(" ").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").includes(q))
    );
    const ranked = [...filtered];
    if (discoverMode === "trending") ranked.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    if (discoverMode === "rated") ranked.sort((a, b) => (b.average ?? -1) - (a.average ?? -1));
    if (discoverMode === "newest") ranked.sort((a, b) =>
      (Date.parse(b.publishedAt || "") || -1) - (Date.parse(a.publishedAt || "") || -1));
    return ranked;
  }, [catalogItems, searchItems, catalogQuery, catalogCategory, catalogSource, discoverMode]);

  /* ───────── Actions ───────── */
  async function applyWallpaper(path: string) {
    if (!path) return;
    setPlaybackBusy(true);
    try {
      await engineRPC("play", { output: selectedOutput, wallpaper: path });
      toast.success(`Wallpaper appliqué sur ${selectedOutput}`);
    } catch (e: any) {
      toast.error(e.message || "Impossible d'appliquer le wallpaper");
    } finally {
      setPlaybackBusy(false);
    }
  }

  async function toggleFavorite(id: number, current: boolean) {
    try {
      await engineRPC("library.set_favorite", { id, favorite: !current });
      void loadLibrary();
      toast.success(!current ? "Ajouté aux favoris" : "Retiré des favoris");
    } catch (error: any) {
      toast.error(error?.message || "Impossible de modifier le favori.");
    }
  }

  async function downloadHubItem(item: Item) {
    const mediaUrl = item.engineDownloadUrl || (item.downloadMode === "direct" ? item.downloadUrl : null);
    if (!mediaUrl) {
      toast.error("Cette fiche ne fournit pas de fichier direct importable par Engine.");
      return;
    }
    if (downloadBusyId) return;
    setDownloadBusyId(item.id);
    setDownloadBusyTitle(item.title);
    setDownloadProgress({ downloaded: 0, total: 0 });
    setDownloadPhase("Démarrage du téléchargement…");
    try {
      const started = await engineRPC("hub.v1.download.start", {
        source: item.source,
        media_url: mediaUrl,
        title: item.title,
        category: item.category,
      });
      const taskId = String(started?.task_id || "");
      if (!taskId) throw new Error("Engine n’a pas démarré le téléchargement.");
      setDownloadTaskId(taskId);
      let task: any;
      do {
        await new Promise(resolve => window.setTimeout(resolve, 500));
        task = await engineRPC("task.status", { task_id: taskId });
        setDownloadProgress({
          downloaded: Number(task?.bytes_downloaded) || 0,
          total: Number(task?.total_bytes) || 0,
        });
        setDownloadPhase(typeof task?.phase === "string" ? task.phase : "Traitement du média…");
      } while (task?.state === "queued" || task?.state === "running");
      if (task?.state === "cancelled") {
        toast.info("Téléchargement annulé.");
        return;
      }
      if (task?.state !== "completed") {
        throw new Error(task?.error?.message || "Le téléchargement a échoué.");
      }
      const result = task.result;
      const wallpaperId = Number(result?.wallpaper?.id);
      if (!Number.isSafeInteger(wallpaperId) || wallpaperId < 1) {
        throw new Error("Engine n’a pas indexé le fichier téléchargé.");
      }
      setDownloadedCatalog(current => ({ ...current, [item.id]: wallpaperId }));
      await loadLibrary();
      toast.success("Téléchargé dans la bibliothèque MPVpaper Engine.");
    } catch (error: any) {
      toast.error(error?.message || "Téléchargement Engine impossible.");
    } finally {
      setDownloadBusyId(null);
      setDownloadBusyTitle("");
      setDownloadTaskId(null);
      setDownloadCanceling(false);
      setDownloadProgress({ downloaded: 0, total: 0 });
      setDownloadPhase("Préparation du téléchargement…");
    }
  }

  async function cancelHubDownload() {
    if (!downloadTaskId || downloadCanceling) return;
    setDownloadCanceling(true);
    try {
      await engineRPC("task.cancel", { task_id: downloadTaskId });
    } catch (error: any) {
      setDownloadCanceling(false);
      toast.error(error?.message || "Impossible d’annuler le téléchargement.");
    }
  }

  async function toggleDownloadedFavorite(itemId: string) {
    const wallpaperId = downloadedCatalog[itemId];
    if (!wallpaperId) return;
    const favorite = !favoriteCatalog[itemId];
    try {
      await engineRPC("library.set_favorite", { id: wallpaperId, favorite });
      setFavoriteCatalog(current => ({ ...current, [itemId]: favorite }));
      await loadLibrary();
      toast.success(favorite ? "Ajouté aux favoris Engine." : "Retiré des favoris Engine.");
    } catch (error: any) {
      toast.error(error?.message || "Impossible de modifier le favori.");
    }
  }

  async function applyDownloadedHubItem(itemId: string) {
    const wallpaperId = downloadedCatalog[itemId];
    if (!wallpaperId) return;
    setPlaybackBusy(true);
    try {
      await engineRPC("hub.v1.apply", { wallpaper_id: wallpaperId, output: selectedOutput });
      toast.success(`Wallpaper appliqué sur ${selectedOutput}.`);
    } catch (error: any) {
      toast.error(error?.message || "Impossible d’appliquer le wallpaper.");
    } finally {
      setPlaybackBusy(false);
    }
  }

  async function deleteWallpaper(id: number) {
    try {
      await engineRPC("library.delete", { id });
      setSelectedMedia(current => current?.type === "local" && current.localItem?.id === id ? null : current);
      void loadLibrary();
      toast.success("Wallpaper mis à la corbeille");
    } catch (e: any) {
      toast.error(e.message || "Suppression impossible");
    }
  }

  async function playbackControl(cmd: string) {
    setPlaybackBusy(true);
    try {
      await engineRPC(cmd, { output: selectedOutput });
      const output = playbackControls?.output || (selectedOutput === "*" ? outputs[0] : selectedOutput);
      if (output && inspectedLocal?.type === "video") {
        const state = await engineRPC("get_output_state", { output });
        setPlaybackControls(state);
      }
    } catch (e: any) {
      toast.error(e.message || `Échec : ${cmd}`);
    } finally {
      setPlaybackBusy(false);
    }
  }

  async function createPlaylist() {
    if (!newPlaylistName.trim()) return;
    try {
      await engineRPC("playlists.create", { name: newPlaylistName.trim() });
      const p = await engineRPC("playlists.list");
      setPlaylists(Array.isArray(p) ? p : []);
      setNewPlaylistName("");
      toast.success("Playlist créée");
    } catch (e: any) {
      toast.error(e.message || "Impossible de créer la playlist");
    }
  }

  async function setVolume(vol: number) {
    try {
      const result = await engineRPC("set_volume", { output: playbackControls?.output || selectedOutput, volume: vol });
      setPlaybackControls((current: any) => ({ ...current, volume: result?.volume ?? vol }));
    } catch (error: any) { toast.error(error?.message || "Impossible de régler le volume."); }
  }
  async function setSpeed(spd: number) {
    try {
      const result = await engineRPC("set_speed", { output: playbackControls?.output || selectedOutput, speed: spd });
      setPlaybackControls((current: any) => ({ ...current, speed: result?.speed ?? spd }));
    } catch (error: any) { toast.error(error?.message || "Impossible de régler la vitesse."); }
  }
  async function toggleMute() {
    const output = playbackControls?.output || (selectedOutput === "*" ? outputs[0] : selectedOutput);
    if (!output || !playbackControlsActive) return;
    const muted = !Boolean(playbackControls.muted);
    try {
      const result = await engineRPC("set_mute", { output, muted });
      setPlaybackControls((current: any) => ({ ...current, muted: result?.muted ?? muted }));
    } catch (error: any) { toast.error(error?.message || "Impossible de modifier le mode muet."); }
  }
  async function toggleLoop() {
    const output = playbackControls?.output || (selectedOutput === "*" ? outputs[0] : selectedOutput);
    if (!output || !playbackControlsActive) return;
    const enabled = !Boolean(playbackControls.loop);
    try {
      const result = await engineRPC("set_loop", { output, enabled });
      setPlaybackControls((current: any) => ({ ...current, loop: result?.loop ?? enabled }));
    } catch (error: any) { toast.error(error?.message || "Impossible de modifier la boucle."); }
  }

  /* ───────── Selected Item for Inspector ───────── */
  const inspected = selectedMedia;
  const inspectedLocal = inspected?.type === "local"
    ? libraryItems.find(item => item.id === inspected.localItem?.id) || inspected.localItem
    : null;
  const inspectedCatalog = inspected?.type === "catalog" ? inspected.catalogItem : null;
  const inspectedEngineDownloadUrl = inspectedCatalog?.engineDownloadUrl ||
    (inspectedCatalog?.downloadMode === "direct" ? inspectedCatalog.downloadUrl : null);
  const inspectedTitle = inspectedLocal?.title || inspectedCatalog?.title || "";
  const inspectedPath = inspectedLocal?.path || "";
  const playbackControlsActive = Boolean(playbackControls && playbackControls.status !== "stopped");

  useEffect(() => {
    let current = true;
    if (!engineConnected || inspectedLocal?.type !== "video") {
      setPlaybackControls(null);
      return () => { current = false; };
    }
    const output = selectedOutput === "*" ? outputs[0] : selectedOutput;
    if (!output) {
      setPlaybackControls(null);
      return () => { current = false; };
    }
    setPlaybackControls(null);
    engineRPC("get_output_state", { output })
      .then(state => { if (current) setPlaybackControls(state); })
      .catch(() => { if (current) setPlaybackControls(null); });
    return () => { current = false; };
  }, [engineConnected, inspectedLocal?.id, inspectedLocal?.type, selectedOutput, outputs]);

  useEffect(() => () => {
    if (volumeDebounce.current !== null) window.clearTimeout(volumeDebounce.current);
    if (speedDebounce.current !== null) window.clearTimeout(speedDebounce.current);
  }, []);

  async function importLocalPath() {
    const path = localImportPath.trim();
    if (!path || localImportBusy) return;
    setLocalImportBusy(true);
    try {
      const imported = await engineRPC("library.import", { path, source: "local" });
      if (!imported || !Number.isSafeInteger(imported.id)) {
        throw new Error("Engine n’a pas ajouté le média à sa bibliothèque.");
      }
      setLibraryItems(items => [imported, ...items.filter(item => item.id !== imported.id)]);
      setSelectedMedia({ type: "local", localItem: imported });
      setLocalImportPath("");
      toast.success(`Ajouté à la bibliothèque : ${imported.title}`);
    } catch (error: any) {
      toast.error(error?.message || "Import local impossible.");
    } finally {
      setLocalImportBusy(false);
    }
  }

  /* ───────── Content section title ───────── */
  const sectionTitle: Record<NavSection, string> = {
    library: "Votre bibliothèque",
    live: "Live vidéos",
    images: "Images",
    scenes: "Scènes",
    discover: "Découvrir",
    favorites: "Favoris",
    playlists: "Playlists",
    recent: "Récents",
    monitors: "Écrans",
    settings: "Réglages",
    hud: "Desktop HUD Editor",
  };

  /* ═══════════════════════════════════════════════════════════ */
  /*                         RENDER                              */
  /* ═══════════════════════════════════════════════════════════ */

  return (
    <>
    <Toaster theme="dark" position="bottom-right" />
    {downloadBusyId && (
      <div className="hub-download-toast" role="status" aria-live="polite">
        <strong>{downloadBusyTitle || "Téléchargement Engine"}</strong>
        <div className="engine-download-progress-track">
          <span
            className={downloadProgress.total ? "is-determinate" : ""}
            style={downloadProgress.total ? { width: `${Math.min(100, downloadProgress.downloaded / downloadProgress.total * 100)}%` } : undefined}
          />
        </div>
        <span>
          {downloadProgress.total
            ? `${downloadPhase} · ${Math.min(100, Math.round(downloadProgress.downloaded / downloadProgress.total * 100))}% · ${fmtSize(downloadProgress.downloaded)} / ${fmtSize(downloadProgress.total)}`
            : downloadProgress.downloaded
              ? `${downloadPhase} · ${fmtSize(downloadProgress.downloaded)}`
              : downloadPhase}
        </span>
        <button className="btn-cancel-download" onClick={() => void cancelHubDownload()} disabled={!downloadTaskId || downloadCanceling}>
          <X size={14} /> {downloadCanceling ? "Annulation…" : "Annuler"}
        </button>
      </div>
    )}
    <div className={`hub-3panel${embedded ? " hub-embedded" : ""}`}>
      {/* ═══ LEFT: Navigation Sidebar ═══ */}
      {!embedded && <aside className="hub-sidebar">
        <div className="hub-sidebar-brand">
          <img src="/mpvpaper-engine.png" width={32} height={32} alt="" className="brand-symbol brand-logo" />
          <span className="brand-text">MPVpaper<span className="brand-sub">Engine 2</span></span>
        </div>

        <nav className="hub-sidebar-nav">
          <div className="nav-group">
            <button className={`nav-item ${section === "library" ? "active" : ""}`} onClick={() => setSection("library")}>
              <Layers size={18} /> Bibliothèque
            </button>
          </div>

          <div className="nav-group">
            <div className="nav-label">Catégories</div>
            <button className={`nav-item ${section === "live" ? "active" : ""}`} onClick={() => setSection("live")}>
              <Video size={17} /> Live vidéos
            </button>
            <button className={`nav-item ${section === "images" ? "active" : ""}`} onClick={() => setSection("images")}>
              <Image size={17} /> Images
            </button>
            <button className={`nav-item ${section === "scenes" ? "active" : ""}`} onClick={() => setSection("scenes")}>
              <LayoutGrid size={17} /> Scènes
            </button>
          </div>

          <div className="nav-group">
            <button className={`nav-item ${section === "discover" ? "active" : ""}`} onClick={() => setSection("discover")}>
              <Compass size={18} /> Découvrir
            </button>
          </div>

          <div className="nav-group">
            <button className={`nav-item ${section === "favorites" ? "active" : ""}`} onClick={() => setSection("favorites")}>
              <Heart size={17} /> Favoris
            </button>
            <button className={`nav-item ${section === "playlists" ? "active" : ""}`} onClick={() => setSection("playlists")}>
              <ListMusic size={17} /> Playlists
            </button>
            <button className={`nav-item ${section === "recent" ? "active" : ""}`} onClick={() => setSection("recent")}>
              <History size={17} /> Récents
            </button>
          </div>

          <div className="nav-group">
            <button className={`nav-item ${section === "monitors" ? "active" : ""}`} onClick={() => setSection("monitors")}>
              <Monitor size={17} /> Écrans
            </button>
            <button className={`nav-item ${section === "settings" ? "active" : ""}`} onClick={() => setSection("settings")}>
              <Settings size={17} /> Réglages
            </button>
          </div>

          <div className="nav-group nav-bottom">
            <button className={`nav-item ${section === "hud" ? "active" : ""}`} onClick={() => setSection("hud")}>
              <SlidersHorizontal size={17} /> HUD Editor
            </button>
          </div>
        </nav>

        <div className="hub-sidebar-status">
          {engineConnected === true ? (
            <span className="engine-pill connected"><CheckCircle2 size={13} /> Engine actif</span>
          ) : engineConnected === false ? (
            <span className="engine-pill offline"><AlertTriangle size={13} /> Engine hors ligne</span>
          ) : (
            <span className="engine-pill"><LoaderCircle size={13} className="spin" /> Connexion…</span>
          )}
        </div>
      </aside>}

      {/* ═══ CENTER: Main Content ═══ */}
      <main className="hub-content">
        <div className="content-header">
          <h1>{sectionTitle[section]}</h1>
          {(section === "library" || section === "live" || section === "images" || section === "scenes" || section === "favorites") && (
            <div className="content-search">
              <Search size={16} />
              <input
                placeholder="Rechercher dans la bibliothèque…"
                value={libraryQuery}
                onChange={e => setLibraryQuery(e.target.value)}
              />
              {libraryQuery && <button onClick={() => setLibraryQuery("")}><X size={14} /></button>}
            </div>
          )}
          {section === "discover" && (
            <div className="content-search">
              <Search size={16} />
              <input
                placeholder="Rechercher des wallpapers…"
                value={catalogQuery}
                onChange={e => {
                  setCatalogQuery(e.target.value);
                  setCatalogSource("Toutes les sources");
                  setCatalogCategory("Tous");
                }}
              />
              {catalogQuery && <button onClick={() => setCatalogQuery("")}><X size={14} /></button>}
            </div>
          )}
        </div>

        {/* ── Library / Live / Images / Scenes / Favorites ── */}
        {(section === "library" || section === "live" || section === "images" || section === "scenes" || section === "favorites") && (
          <div className="content-body">
            {section === "library" && (
              <div className="content-filter-row">
                <span className="result-count">{filteredLibrary.length} média{filteredLibrary.length !== 1 ? "s" : ""}</span>
                <button className="btn-sm" onClick={() => void loadLibrary(true)}><RotateCw size={14} /> Actualiser</button>
              </div>
            )}
            {libraryLoading ? (
              <div className="grid-loading"><LoaderCircle size={24} className="spin" /> Chargement de la bibliothèque…</div>
            ) : filteredLibrary.length === 0 ? (
              <div className="empty-state">
                <Layers size={40} />
                <p>Aucun média trouvé</p>
                <span>Ajoutez des wallpapers dans ~/Pictures/Wallpapers ou ~/Videos/Wallpapers</span>
              </div>
            ) : (
              <div className="media-grid">
                {filteredLibrary.map(item => (
                  <article
                    key={item.id}
                    className={`media-card ${selectedMedia?.type === "local" && selectedMedia.localItem?.id === item.id ? "selected" : ""}`}
                    onClick={() => setSelectedMedia({ type: "local", localItem: item })}
                  >
                    <div className="media-thumb">
                      <Thumb item={{ title: item.title, thumbnail_path: item.thumbnail_path, source: item.type }} />
                      <span className="res-pill">{fmtRes(item.width, item.height)}</span>
                      {item.favorite && <span className="fav-badge"><Heart size={12} fill="currentColor" /></span>}
                      {item.missing && <span className="missing-badge">Manquant</span>}
                    </div>
                    <div className="media-info">
                      <div className="media-title">{item.title}</div>
                      <div className="media-meta">
                        <span>{item.type === "video" ? "Vidéo" : item.type === "image" ? "Image" : item.type === "scene" ? "Scène" : item.type}</span>
                        {item.duration ? <span>{fmtDuration(item.duration)}</span> : null}
                        <span>{fmtSize(item.file_size)}</span>
                        {item.fps ? <span>{item.fps} FPS</span> : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Discover (merged Projet Web + Découvrir) ── */}
        {section === "discover" && (
          <div className="content-body">
            <nav className="hub-subnav" aria-label="Sections de découverte">
              {DISCOVER_MODES.map(([mode, label]) => (
                <button key={mode} className={`hub-tab-btn ${discoverMode === mode ? "active" : ""}`} onClick={() => setDiscoverMode(mode)}>
                  {label}
                </button>
              ))}
            </nav>
            <div className="discover-categories">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  className={`category ${catalogCategory === cat ? "active" : ""}`}
                  onClick={() => setCatalogCategory(cat)}
                >{cat}</button>
              ))}
              <select className="btn-sm" aria-label="Filtrer par source" value={catalogSource}
                onChange={event => setCatalogSource(event.target.value)}>
                <option>Toutes les sources</option>
                {Array.from(new Set([...catalogItems, ...searchItems].map(item => item.source))).map(source =>
                  <option key={source}>{source}</option>
                )}
              </select>
            </div>

            {catalogQuery.trim().length >= 2 && (
              <div className="search-source-status" role="status" aria-live="polite">
                {searchLoading && <span className="searching-label"><LoaderCircle size={14} className="spin" /> Recherche multi-sources…</span>}
                {!searchLoading && searchSources.map((source: any) => (
                  <span className={`source-health ${source.status}`} key={source.id}>
                    {source.name}: {source.status === "available" ? `${source.count} résultat${source.count === 1 ? "" : "s"}` : source.status === "rate_limited" ? "limite temporaire" : "indisponible"}
                  </span>
                ))}
              </div>
            )}

            {/* Recommendations from Engine */}
            {!embedded && recommendations.length > 0 && (
              <div className="discover-section">
                <h3><Sparkles size={16} /> Recommandations Engine</h3>
                <div className="media-grid compact">
                  {recommendations.map((r, i) => (
                    <article key={i} className="media-card" onClick={() =>
                      setSelectedMedia({ type: "catalog", catalogItem: { ...r, id: r.uri, source: r.source, tags: r.tags || [], category: "", downloadMode: "redirect", downloadUrl: "", sourceUrl: r.uri, previewUrl: "", width: 0, height: 0, checkedAt: "", sourcePolicy: "", sourcePolicyUrl: "", favorites: 0, votes: 0, average: r.rating, downloads: 0, views: 0, weekly: 0, score: r.rating, favorite: false, rating: r.rating } as any })
                    }>
                      <div className="media-thumb">
                        <Thumb item={{ title: r.title, thumbnail: r.thumbnail, source: r.source }} />
                      </div>
                      <div className="media-info">
                        <div className="media-title">{r.title}</div>
                        <div className="media-meta"><span>{r.source}</span></div>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            )}

            {/* Catalog from Hub */}
            <div className="discover-section">
              <h3><Globe size={16} /> Catalogue · {filteredCatalog.length} fonds disponibles</h3>
              {catalogLoading ? (
                <div className="grid-loading"><LoaderCircle size={24} className="spin" /> Chargement…</div>
              ) : (
                <div className="media-grid">
                  {filteredCatalog.map(w => (
                    <article
                      key={w.id}
                      className={`media-card ${selectedMedia?.type === "catalog" && selectedMedia.catalogItem?.id === w.id ? "selected" : ""}`}
                      onClick={() => setSelectedMedia({ type: "catalog", catalogItem: w })}
                    >
                      <div className="media-thumb">
                        <Thumb item={w} />
                        {w.width && w.height ? <span className="res-pill">{fmtRes(w.width, w.height)}</span> : null}
                        {(w.downloadMode === "direct" || w.engineDownloadUrl) && <span className="dl-badge"><Download size={10} /></span>}
                      </div>
                      <div className="media-info">
                        <div className="media-source" style={{ color: SOURCE_COLORS[w.source] || "#a5b4c7" }}>{w.source}</div>
                        <div className="media-title">{w.title}</div>
                        <div className="media-meta">
                          {w.score !== null && <span className="score-val">★ {w.score.toFixed(1)}</span>}
                          <span>{w.downloads} DL</span>
                        </div>
                      </div>
                      {(w.downloadMode === "direct" || w.engineDownloadUrl) && (
                        <button
                          className="media-download-action"
                          disabled={!engineConnected || downloadBusyId !== null}
                          onClick={event => {
                            event.stopPropagation();
                            void downloadHubItem(w);
                          }}
                          aria-label={`Télécharger ${w.title} dans la bibliothèque Engine`}
                        >
                          <Download size={14} />
                          {downloadBusyId === w.id ? "Téléchargement…" : "Télécharger"}
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>

            {!catalogLoading && searchLoading && catalogQuery.trim().length >= 2 && filteredCatalog.length === 0 && (
              <div className="empty-state"><LoaderCircle size={30} className="spin" /><p>Recherche en cours…</p><span>Les résultats arrivent dès que les sources répondent.</span></div>
            )}
            {!catalogLoading && !searchLoading && filteredCatalog.length === 0 && (
              <div className="empty-state">
                <Compass size={40} />
                <p>{discoverMode === "newest" ? "Aucune date de publication vérifiée" : "Aucun résultat"}</p>
                <span>{discoverMode === "newest" ? "Les sources n’ont pas fourni de date de publication exploitable pour cette sélection." : "Essayez d'autres mots-clés, sources ou catégories."}</span>
              </div>
            )}
          </div>
        )}

        {/* ── Playlists ── */}
        {section === "playlists" && (
          <div className="content-body">
            <div className="playlist-create">
              <input placeholder="Nom de la playlist…" value={newPlaylistName} onChange={e => setNewPlaylistName(e.target.value)} />
              <button className="btn-primary" onClick={createPlaylist}><Plus size={14} /> Créer</button>
            </div>
            {playlists.length === 0 ? (
              <div className="empty-state"><ListMusic size={40} /><p>Aucune playlist</p><span>Créez votre première playlist ci-dessus</span></div>
            ) : (
              <div className="playlist-list">
                {playlists.map((p: any) => (
                  <div key={p.id} className="playlist-card">
                    <ListMusic size={20} />
                    <div><strong>{p.name}</strong><span>{p.items?.length || 0} éléments · {p.mode}</span></div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Recent ── */}
        {section === "recent" && (
          <div className="content-body">
            <div className="empty-state"><History size={40} /><p>Historique récent</p><span>Les wallpapers récemment appliqués apparaîtront ici</span></div>
          </div>
        )}

        {/* ── Monitors ── */}
        {section === "monitors" && (
          <div className="content-body">
            <div className="monitors-list">
              {outputs.length === 0 ? (
                <div className="empty-state"><Monitor size={40} /><p>Aucun écran détecté</p><span>{engineConnected ? "Hyprland ne semble pas actif" : "Démarrez Engine pour détecter les écrans"}</span></div>
              ) : outputs.map(o => (
                <div key={o} className={`monitor-entry ${selectedOutput === o ? "active" : ""}`} onClick={() => setSelectedOutput(o)}>
                  <Monitor size={20} />
                  <div><strong>{o}</strong><span>{selectedOutput === o ? "Sélectionné" : "Cliquer pour sélectionner"}</span></div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Settings ── */}
        {section === "settings" && (
          <div className="content-body settings-panel">
            <div className="settings-group">
              <h3>État Engine</h3>
              <div className="setting-row"><span>Connexion</span><span>{engineConnected ? "Actif" : "Hors ligne"}</span></div>
              {engineInfo && <>
                <div className="setting-row"><span>PID</span><span>{engineInfo.pid}</span></div>
                <div className="setting-row"><span>Version</span><span>{engineInfo.engine_version || engineInfo.version}</span></div>
                <div className="setting-row"><span>Tâches actives</span><span>{engineInfo.active_tasks_count ?? 0}</span></div>
              </>}
            </div>
            <div className="settings-group">
              <h3>Écran actif</h3>
              <Select value={selectedOutput} onValueChange={setSelectedOutput}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="*">Tous les écrans (*)</SelectItem>
                  {outputs.map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        {/* ── HUD Editor ── */}
        {section === "hud" && (
          <div className="content-body">
            <div className="empty-state"><SlidersHorizontal size={40} /><p>Desktop HUD Editor</p><span>Configurez l'affichage HUD depuis Engine directement</span></div>
          </div>
        )}
      </main>

      {/* ═══ RIGHT: Inspector Panel ═══ */}
      <aside className="hub-inspector">
        <div className="inspector-header"><h2>Inspecteur</h2></div>

        {!selectedMedia ? (
          <div className="inspector-empty">
            <Eye size={32} />
            <p>Sélectionnez un wallpaper</p>
            <span>Choisissez un média dans la bibliothèque ou dans Découvrir pour voir ses détails ici</span>
          </div>
        ) : (
          <div className="inspector-content">
            {/* Preview */}
            <div className="inspector-preview">
              {inspectedLocal ? (
                <Thumb item={{ title: inspectedLocal.title, thumbnail_path: inspectedLocal.thumbnail_path, source: inspectedLocal.type }} />
              ) : inspectedCatalog ? (
                catalogPreviewPlaying && inspectedCatalog.previewEmbedUrl ? (
                  <iframe src={inspectedCatalog.previewEmbedUrl} title={`Aperçu YouTube : ${inspectedCatalog.title}`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />
                ) : <><Thumb item={inspectedCatalog} />{inspectedCatalog.previewEmbedUrl && <button className="inspector-preview-play" onClick={() => setCatalogPreviewPlaying(true)}><Play size={18} fill="currentColor" /> Lire l’aperçu YouTube</button>}</>
              ) : null}
            </div>

            {/* Title & meta */}
            <div className="inspector-details">
              <h3>{inspectedTitle}</h3>
              {inspectedLocal && (
                <>
                  <div className="inspector-meta">
                    <div><span>Type</span><strong>{inspectedLocal.type === "video" ? "Vidéo" : inspectedLocal.type === "image" ? "Image" : inspectedLocal.type}</strong></div>
                    <div><span>Résolution</span><strong>{fmtRes(inspectedLocal.width, inspectedLocal.height)}</strong></div>
                    {inspectedLocal.fps && <div><span>FPS</span><strong>{inspectedLocal.fps}</strong></div>}
                    {inspectedLocal.duration && <div><span>Durée</span><strong>{fmtDuration(inspectedLocal.duration)}</strong></div>}
                    <div><span>Taille</span><strong>{fmtSize(inspectedLocal.file_size)}</strong></div>
                    <div><span>Source</span><strong>{inspectedLocal.source}</strong></div>
                    {inspectedLocal.video_codec && <div><span>Codec</span><strong>{inspectedLocal.video_codec}</strong></div>}
                  </div>
                  <div className="inspector-path">{inspectedLocal.path}</div>
                </>
              )}
              {inspectedCatalog && (
                <div className="inspector-meta">
                  <div><span>Source</span><strong style={{ color: SOURCE_COLORS[inspectedCatalog.source] }}>{inspectedCatalog.source}</strong></div>
                  {inspectedCatalog.width && inspectedCatalog.height && <div><span>Résolution</span><strong>{inspectedCatalog.width}×{inspectedCatalog.height}</strong></div>}
                  <div><span>Catégorie</span><strong>{inspectedCatalog.category || "Non communiquée"}</strong></div>
                  <div><span>Téléchargement</span><strong>
                    {inspectedCatalog.engineDownloadUrl || inspectedCatalog.downloadMode === "direct" ? "Téléchargement avec progression Engine" :
                      inspectedCatalog.downloadMode === "steam" ? "Steam Workshop" : "Depuis la page source"}
                  </strong></div>
                  <div><span>Taille</span><strong>{inspectedCatalog.sizeMB ? `${inspectedCatalog.sizeMB} Mo` : "Non communiquée"}</strong></div>
                  {inspectedCatalog.score !== null && <div><span>Score</span><strong>★ {inspectedCatalog.score.toFixed(1)}</strong></div>}
                  {!inspectedCatalog.external && <div><span>Téléchargements Hub</span><strong>{inspectedCatalog.downloads}</strong></div>}
                  {!inspectedCatalog.external && <div><span>Favoris Hub</span><strong>{inspectedCatalog.favorites}</strong></div>}
                  <div><span>Auteur indiqué</span><strong>{inspectedCatalog.author || "Non indiqué par la source"}</strong></div>
                  {inspectedCatalog.tags.length > 0 && <div className="inspector-tags">{inspectedCatalog.tags.map(t => <span key={t}>#{t}</span>)}</div>}
                  {inspectedCatalog.external && <div className="inspector-policy">{inspectedCatalog.sourcePolicy}</div>}
                </div>
              )}
            </div>

            {/* Import a local file or Engine project by path */}
            <div className="inspector-section">
              <label htmlFor="inspector-import-path">Chemin local du média ou projet Engine</label>
              <input
                id="inspector-import-path"
                className="inspector-import-input"
                value={localImportPath}
                onChange={event => setLocalImportPath(event.target.value)}
                onKeyDown={event => { if (event.key === "Enter") void importLocalPath(); }}
                placeholder="/home/utilisateur/Vidéos/fond.mp4"
                aria-label="Chemin local du média ou projet Engine"
              />
              <button className="btn-ghost" disabled={!engineConnected || localImportBusy || !localImportPath.trim()} onClick={() => void importLocalPath()}>
                <FolderOpen size={15} /> {localImportBusy ? "Import en cours…" : "Importer dans la bibliothèque"}
              </button>
            </div>

            {/* Screen selection */}
            <div className="inspector-section">
              <label>Écran cible</label>
              <Select value={selectedOutput} onValueChange={setSelectedOutput}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="*">Tous les écrans (*)</SelectItem>
                  {outputs.map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {/* Apply button */}
            {inspectedLocal && (
              <button
                className="btn-apply"
                disabled={playbackBusy || inspectedLocal.missing}
                onClick={() => applyWallpaper(inspectedLocal.path)}
              >
                <Play size={16} /> Appliquer le fond
              </button>
            )}
            {inspectedCatalog && inspectedEngineDownloadUrl && (
              <div className="engine-hub-actions">
                <button className="btn-apply" disabled={!engineConnected || downloadBusyId !== null} onClick={() => void downloadHubItem(inspectedCatalog)}>
                  <Download size={16} /> {downloadBusyId === inspectedCatalog.id ? "Téléchargement dans Engine…" : "Télécharger dans la bibliothèque Engine"}
                </button>
                {downloadedCatalog[inspectedCatalog.id] && (
                  <>
                    <button className="btn-apply" disabled={playbackBusy} onClick={() => void applyDownloadedHubItem(inspectedCatalog.id)}>
                      <Play size={16} /> Appliquer le wallpaper
                    </button>
                    <button className={`btn-fav ${favoriteCatalog[inspectedCatalog.id] ? "is-fav" : ""}`} onClick={() => void toggleDownloadedFavorite(inspectedCatalog.id)}>
                      <Heart size={15} fill={favoriteCatalog[inspectedCatalog.id] ? "currentColor" : "none"} />
                      {favoriteCatalog[inspectedCatalog.id] ? "Retirer des favoris Engine" : "Ajouter aux favoris Engine"}
                    </button>
                  </>
                )}
                {!engineConnected && <p className="engine-action-note">Démarrez le service MPVpaper Engine pour télécharger, appliquer ou synchroniser les favoris.</p>}
              </div>
            )}
            {inspectedCatalog && inspectedCatalog.sourceUrl && (
              <a className="btn-secondary-link" href={inspectedCatalog.sourceUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} /> Voir la source
              </a>
            )}

            {/* Playback controls */}
            {inspectedLocal && inspectedLocal.type === "video" && (
              <div className="inspector-section">
                <label>Lecture</label>
                <div className="playback-controls">
                  <button onClick={() => playbackControl("pause")} title="Pause" disabled={!playbackControlsActive}><Pause size={16} /></button>
                  <button onClick={() => playbackControl("resume")} title="Reprendre" disabled={!playbackControlsActive}><Play size={16} /></button>
                  <button onClick={() => playbackControl("restart")} title="Relancer" disabled={!playbackControlsActive}><RotateCw size={16} /></button>
                  <button onClick={() => playbackControl("stop")} title="Arrêter" disabled={!playbackControlsActive}><Square size={16} /></button>
                  <button onClick={() => void toggleMute()} title={playbackControls?.muted ? "Activer le son" : "Couper le son"} disabled={!playbackControlsActive}>
                    {playbackControls?.muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
                  </button>
                  <button onClick={() => void toggleLoop()} title={playbackControls?.loop ? "Désactiver la boucle" : "Activer la boucle"} disabled={!playbackControlsActive} aria-pressed={Boolean(playbackControls?.loop)}>
                    <RotateCw size={16} />
                  </button>
                </div>
              </div>
            )}

            {/* Favorite & delete */}
            {inspectedLocal && (
              <div className="inspector-section inspector-actions">
                <button
                  className={`btn-fav ${inspectedLocal.favorite ? "is-fav" : ""}`}
                  onClick={() => toggleFavorite(inspectedLocal.id, inspectedLocal.favorite)}
                >
                  <Heart size={15} fill={inspectedLocal.favorite ? "currentColor" : "none"} />
                  {inspectedLocal.favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
                </button>
                <button className="btn-delete" onClick={() => {
                  if (confirm(`Mettre « ${inspectedLocal.title} » à la corbeille ?`)) deleteWallpaper(inspectedLocal.id);
                }}>
                  <Trash2 size={15} /> Corbeille
                </button>
              </div>
            )}

            {/* Volume & Speed */}
            {inspectedLocal && inspectedLocal.type === "video" && (
              <div className="inspector-section">
                <label>Commandes de lecture · {playbackControls?.output || "état indisponible"}</label>
                {playbackControls?.path && <span className="inspector-playback-path">{playbackControls.path}</span>}
                <label>Volume · {playbackControls?.volume ?? "—"}%</label>
                <input
                  type="range" min="0" max="100" step="1"
                  value={playbackControls?.volume ?? 0}
                  disabled={!playbackControlsActive || playbackControls?.volume == null}
                  onChange={event => {
                    const value = Number(event.target.value);
                    setPlaybackControls((current: any) => current ? { ...current, volume: value } : current);
                    if (volumeDebounce.current !== null) window.clearTimeout(volumeDebounce.current);
                    volumeDebounce.current = window.setTimeout(() => { volumeDebounce.current = null; void setVolume(value); }, 120);
                  }}
                />
                <label>Vitesse · {playbackControls?.speed?.toFixed?.(1) ?? "—"}×</label>
                <input
                  type="range" min="0.1" max="3" step="0.1"
                  value={playbackControls?.speed ?? 1}
                  disabled={!playbackControlsActive || playbackControls?.speed == null}
                  onChange={event => {
                    const value = Number(event.target.value);
                    setPlaybackControls((current: any) => current ? { ...current, speed: value } : current);
                    if (speedDebounce.current !== null) window.clearTimeout(speedDebounce.current);
                    speedDebounce.current = window.setTimeout(() => { speedDebounce.current = null; void setSpeed(value); }, 120);
                  }}
                />
                {!playbackControlsActive && <span className="dim-label">Aucune lecture MPV active pour cet écran.</span>}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
    </>
  );
}
