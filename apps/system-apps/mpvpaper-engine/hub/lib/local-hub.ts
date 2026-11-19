/**
 * MPVpaper Hub — Local State, System Adapters, and Content Optimization.
 *
 * Implements the 9 unified functional areas of MPVpaper Hub:
 * 1. Découverte (sources and catalog exploration)
 * 2. Suggestions IA (wallpaper recommendations)
 * 3. Hub personnel (preferences, tastes, playlists, history)
 * 4. Projets Web (catalog and web wallpapers management, including CEF security sandboxing status)
 * 5. Bibliothèque (local media management: images, videos, scenes, downloads)
 * 6. Optimisation (manual content preparation: 720p/150MB initial profile, no auto-downgrade, preserving originals)
 * 7. Écran de verrouillage (modular adapters: Hyprland, GNOME, KDE, unsupported fallback)
 * 8. Écran de veille (screensaver timeout, content, preview)
 * 9. Gestion des écrans (per-monitor settings, visual layout preview)
 */

export type MediaType = "video" | "image" | "scene" | "web";

export interface LocalMediaItem {
  id: string;
  title: string;
  type: MediaType;
  path: string;
  thumbnail?: string;
  category: string;
  tags: string[];
  resolution?: string;
  sizeMB?: number;
  duration?: number;
  fps?: number;
  codec?: string;
  favorite: boolean;
  importedAt: string;
}

export interface Playlist {
  id: string;
  name: string;
  itemIds: string[];
  intervalSeconds: number;
  shuffle: boolean;
  createdAt: string;
}

export interface HistoryEntry {
  id: string;
  title: string;
  source: string;
  timestamp: string;
  output?: string;
}

export interface WebProject {
  id: string;
  title: string;
  author: string;
  source: string;
  previewUrl: string;
  status: "sandboxed" | "blocked_policy" | "compatible" | "review_needed";
  statusLabel: string;
  description: string;
  tags: string[];
}

export interface MonitorConfig {
  name: string;
  model: string;
  width: number;
  height: number;
  refreshRate: number;
  scale: number;
  x: number;
  y: number;
  focused: boolean;
  wallpaperPath?: string;
  wallpaperTitle?: string;
  fitMode: "fit" | "fill" | "stretch" | "center";
  volume: number;
  muted: boolean;
  fpsLimit: number;
}

export interface LockscreenConfig {
  adapter: "Hyprland" | "GNOME" | "KDE" | "Generic";
  supported: boolean;
  toolName: string;
  wallpaperPath: string;
  wallpaperTitle: string;
  blurPasses: number;
  blurSize: number;
  previewActive: boolean;
  distinctFromDesktop: boolean;
}

export interface ScreensaverConfig {
  adapter: "Hyprland" | "GNOME" | "KDE" | "Generic";
  supported: boolean;
  toolName: string;
  wallpaperPath: string;
  wallpaperTitle: string;
  idleDelayMinutes: number;
  dpmsOff: boolean;
  previewActive: boolean;
}

export interface VideoOptimizerParams {
  resolution: "original" | "4k" | "1440p" | "1080p" | "720p";
  fps: "original" | "60" | "30" | "24";
  codec: "h264" | "hevc";
  compression: "weak" | "medium" | "strong";
  targetMaxMB: number;
  preserveOriginal: true;
}

export interface ImageOptimizerParams {
  resolution: "original" | "4k" | "1440p" | "1080p" | "720p";
  format: "png" | "jpeg" | "webp" | "avif";
  compression: "weak" | "medium" | "strong";
  targetMaxMB: number;
  preserveOriginal: true;
}

export interface OptimizationEstimate {
  originalResolution: string;
  targetResolution: string;
  originalSizeMB: number;
  estimatedSizeMB: number;
  requiresLossyConfirmation: boolean;
  codecOrFormat: string;
  summary: string;
}

export const INITIAL_OPTIMIZER_VIDEO: VideoOptimizerParams = {
  resolution: "720p",
  fps: "original",
  codec: "h264",
  compression: "medium",
  targetMaxMB: 150,
  preserveOriginal: true,
};

export const INITIAL_OPTIMIZER_IMAGE: ImageOptimizerParams = {
  resolution: "720p",
  format: "webp",
  compression: "medium",
  targetMaxMB: 150,
  preserveOriginal: true,
};

export const DEFAULT_WEB_PROJECTS: WebProject[] = [
  {
    id: "web-shader-cyber",
    title: "Cyberpunk Neon Grid (WebGL)",
    author: "Kolemm14 Lab",
    source: "Projet Web Local",
    previewUrl: "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=600&auto=format&fit=crop&q=80",
    status: "blocked_policy",
    statusLabel: "Exécution bloquée · Validation de sécurité CEF requise",
    description: "Projet web interactif canvas Shader. L'exécution de code Web non sandboxé est désactivée par défaut pour garantir la stabilité et la sécurité du bureau.",
    tags: ["web", "shader", "cyberpunk", "interactif"],
  },
  {
    id: "web-rain-matrix",
    title: "Matrix Digital Rain HTML5",
    author: "Community",
    source: "Lively Web Wallpaper",
    previewUrl: "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&auto=format&fit=crop&q=80",
    status: "blocked_policy",
    statusLabel: "Exécution bloquée · Sandbox requise",
    description: "Pluie de code numérique. Requiert un runtime sécurisé WebEngine isolé sans accès réseau direct.",
    tags: ["web", "matrix", "retro", "code"],
  },
  {
    id: "web-audio-visualizer",
    title: "Audio Reactive Waves",
    author: "Hugo Santos Dedication",
    source: "Projet Web Local",
    previewUrl: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
    status: "review_needed",
    statusLabel: "En attente de conteneurisation",
    description: "Visualiseur de spectre audio HTML5 / WebAudio. Prévu pour intégration Cava / Waybar via protocole IPC.",
    tags: ["web", "audio", "reactive", "waves"],
  },
];

export const DEFAULT_LOCAL_LIBRARY: LocalMediaItem[] = [
  {
    id: "lib-lofi-night",
    title: "Lofi Night Study Room",
    type: "video",
    path: "~/Vidéos/Wallpapers/lofi_night_study.mp4",
    thumbnail: "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=600&auto=format&fit=crop&q=80",
    category: "Anime",
    tags: ["anime", "calme", "lofi", "pluie"],
    resolution: "1920x1080",
    sizeMB: 84.5,
    duration: 32,
    fps: 30,
    codec: "h264",
    favorite: true,
    importedAt: "2026-10-15T14:20:00Z",
  },
  {
    id: "lib-aurora-borealis",
    title: "Fjord & Aurore Boréale",
    type: "video",
    path: "~/Vidéos/Wallpapers/aurora_fjord_4k.mp4",
    thumbnail: "https://images.unsplash.com/photo-1531366936337-7c912a4589a7?w=600&auto=format&fit=crop&q=80",
    category: "Nature",
    tags: ["nature", "espace", "aurora", "montagne"],
    resolution: "3840x2160",
    sizeMB: 340.2,
    duration: 60,
    fps: 60,
    codec: "hevc",
    favorite: false,
    importedAt: "2026-10-20T09:12:00Z",
  },
  {
    id: "lib-tokyo-neon",
    title: "Shinjuku Rain Alley",
    type: "image",
    path: "~/Images/Wallpapers/shinjuku_neon.png",
    thumbnail: "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=600&auto=format&fit=crop&q=80",
    category: "Ville",
    tags: ["ville", "cyberpunk", "tokyo", "pluie"],
    resolution: "2560x1440",
    sizeMB: 18.2,
    favorite: true,
    importedAt: "2026-10-28T18:45:00Z",
  },
  {
    id: "lib-deep-space-nebula",
    title: "Cosmic Pillars Nebula",
    type: "scene",
    path: "~/Vidéos/Wallpapers/nebula_scene.mpvp",
    thumbnail: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop&q=80",
    category: "Espace",
    tags: ["espace", "galaxie", "calme"],
    resolution: "3840x2160",
    sizeMB: 195.0,
    favorite: false,
    importedAt: "2026-11-01T11:00:00Z",
  },
];

export const DEFAULT_MONITORS: MonitorConfig[] = [
  {
    name: "eDP-1",
    model: "Écran Principal Portable (16:10)",
    width: 2560,
    height: 1600,
    refreshRate: 165,
    scale: 1.25,
    x: 0,
    y: 0,
    focused: true,
    wallpaperPath: "~/Vidéos/Wallpapers/lofi_night_study.mp4",
    wallpaperTitle: "Lofi Night Study Room",
    fitMode: "fill",
    volume: 0,
    muted: true,
    fpsLimit: 60,
  },
  {
    name: "HDMI-A-1",
    model: "Moniteur Externe 4K UltraHD",
    width: 3840,
    height: 2160,
    refreshRate: 60,
    scale: 1.5,
    x: 2560,
    y: 0,
    focused: false,
    wallpaperPath: "~/Vidéos/Wallpapers/aurora_fjord_4k.mp4",
    wallpaperTitle: "Fjord & Aurore Boréale",
    fitMode: "fill",
    volume: 35,
    muted: false,
    fpsLimit: 60,
  },
];

export function estimateVideoOptimization(
  meta: { width: number; height: number; sizeMB: number; fps?: number },
  params: VideoOptimizerParams
): OptimizationEstimate {
  const resMap: Record<string, [number, number]> = {
    "4k": [3840, 2160],
    "1440p": [2560, 1440],
    "1080p": [1920, 1080],
    "720p": [1280, 720],
  };

  const origPixels = meta.width * meta.height;
  const targetDims = params.resolution === "original" ? [meta.width, meta.height] : resMap[params.resolution];
  const targetPixels = targetDims[0] * targetDims[1];
  const scaleRatio = Math.min(1.0, targetPixels / Math.max(1, origPixels));

  const origFps = meta.fps || 30;
  const targetFps = params.fps === "original" ? origFps : parseInt(params.fps, 10);
  const fpsRatio = Math.min(1.0, targetFps / Math.max(1, origFps));

  const compRatios = { weak: 0.85, medium: 0.65, strong: 0.45 };
  const codecRatios = { h264: 1.0, hevc: 0.70 };

  const rawEstimated = meta.sizeMB * scaleRatio * fpsRatio * compRatios[params.compression] * codecRatios[params.codec];
  const cappedEstimated = Math.min(Number(rawEstimated.toFixed(1)), params.targetMaxMB);
  const requiresLossy = scaleRatio < 0.98 || fpsRatio < 0.98 || params.compression !== "weak";

  return {
    originalResolution: `${meta.width}x${meta.height}`,
    targetResolution: `${targetDims[0]}x${targetDims[1]}`,
    originalSizeMB: meta.sizeMB,
    estimatedSizeMB: cappedEstimated,
    requiresLossyConfirmation: requiresLossy,
    codecOrFormat: params.codec.toUpperCase(),
    summary: `Résolution ${targetDims[0]}x${targetDims[1]} (${params.resolution}), ${targetFps} FPS, codec ${params.codec.toUpperCase()}, compression ${params.compression}. Taille estimée : ~${cappedEstimated} Mo (plafond: ${params.targetMaxMB} Mo).`,
  };
}

export function estimateImageOptimization(
  meta: { width: number; height: number; sizeMB: number },
  params: ImageOptimizerParams
): OptimizationEstimate {
  const resMap: Record<string, [number, number]> = {
    "4k": [3840, 2160],
    "1440p": [2560, 1440],
    "1080p": [1920, 1080],
    "720p": [1280, 720],
  };

  const origPixels = meta.width * meta.height;
  const targetDims = params.resolution === "original" ? [meta.width, meta.height] : resMap[params.resolution];
  const targetPixels = targetDims[0] * targetDims[1];
  const scaleRatio = Math.min(1.0, targetPixels / Math.max(1, origPixels));

  const formatRatios: Record<string, number> = { png: 1.0, jpeg: 0.55, webp: 0.40, avif: 0.30 };
  const compRatios = { weak: 0.92, medium: 0.78, strong: 0.60 };

  const rawEstimated = meta.sizeMB * scaleRatio * formatRatios[params.format] * compRatios[params.compression];
  const cappedEstimated = Math.min(Number(rawEstimated.toFixed(1)), params.targetMaxMB);
  const requiresLossy = scaleRatio < 0.98 || params.format !== "png" || params.compression !== "weak";

  return {
    originalResolution: `${meta.width}x${meta.height}`,
    targetResolution: `${targetDims[0]}x${targetDims[1]}`,
    originalSizeMB: meta.sizeMB,
    estimatedSizeMB: cappedEstimated,
    requiresLossyConfirmation: requiresLossy,
    codecOrFormat: params.format.toUpperCase(),
    summary: `Format ${params.format.toUpperCase()}, résolution ${targetDims[0]}x${targetDims[1]}, compression ${params.compression}. Taille estimée : ~${cappedEstimated} Mo.`,
  };
}
