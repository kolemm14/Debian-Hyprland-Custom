import { catalogFor, identity, wallpapers } from "@/lib/hub";
import { searchExternalWallpapers, type SearchWallpaper, type SourceStatus } from "@/lib/sources/wallpaper-search";

function normalize(value: string) {
  return value.toLocaleLowerCase("fr").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function fallbackStats() {
  return wallpapers.map((wallpaper) => ({
    ...wallpaper,
    favorites: 0,
    votes: 0,
    average: null,
    views: 0,
    downloads: 0,
    weekly: 0,
    score: null,
    favorite: false,
    rating: null,
  }));
}

export async function GET(request: Request) {
  const user = identity(request);
  const headers = {
    "Cache-Control": "private, no-store",
    ...(user.cookie ? { "Set-Cookie": user.cookie } : {}),
  };
  const rawQuery = new URL(request.url).searchParams.get("q") || "";
  const query = rawQuery.trim().replace(/[\u0000-\u001f\u007f]/g, "").slice(0, 120);
  if (query.length < 2) {
    return Response.json({ items: [], sources: [], signedIn: user.signedIn, statsAvailable: true }, { headers });
  }

  const queryKey = normalize(query);
  const localItems = wallpapers.filter((wallpaper) =>
    normalize([wallpaper.title, wallpaper.source, ...wallpaper.tags].join(" ")).includes(queryKey)
  );
  const externalPromise = searchExternalWallpapers(query, fetch, request.signal);
  let catalogItems = fallbackStats();
  let statsAvailable = false;
  try {
    catalogItems = await catalogFor(user.id);
    statsAvailable = true;
  } catch (error) {
    console.error("Recherche locale : statistiques indisponibles", error);
  }
  const localById = new Map(catalogItems.map((item) => [item.id, item]));
  const localResults = localItems.map((item) => localById.get(item.id)!).filter(Boolean);
  const external = await externalPromise;
  const sources: SourceStatus[] = [
    { id: "catalogue", name: "Catalogue MPVpaper", status: "available", count: localResults.length },
    ...external.sources,
  ];

  const seen = new Set(localResults.map((item) => item.sourceUrl.replace(/\/$/, "").toLowerCase()));
  const uniqueExternal: SearchWallpaper[] = [];
  for (const item of external.items) {
    const key = item.sourceUrl.replace(/\/$/, "").toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueExternal.push(item);
  }

  return Response.json({
    items: [...localResults, ...uniqueExternal],
    sources,
    signedIn: user.signedIn,
    statsAvailable,
  }, { headers });
}
