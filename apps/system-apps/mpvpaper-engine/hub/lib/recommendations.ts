import { z } from "zod";

// A closed, public vocabulary prevents local filenames or personal tags being sent.
export const PREFERENCE_TAGS = ["anime", "jeux", "nature", "ville", "espace", "paysage", "calme", "ciel", "your name", "cyberpunk", "pluie", "foret", "montagne", "mer", "neige", "fantasy"] as const;
const profileSchema = z.object({
  version: z.literal(1),
  source: z.literal("mpvpaper-engine"),
  preferences: z.array(z.object({tag: z.enum(PREFERENCE_TAGS), weight: z.number().finite().min(0.01).max(1)}).strict()).max(PREFERENCE_TAGS.length),
}).strict();
export type EngineProfile = z.infer<typeof profileSchema>;
export function parseEngineProfile(text: string): EngineProfile {
  if (new TextEncoder().encode(text).byteLength > 4096) throw new Error("Le profil Engine est trop volumineux.");
  let payload: unknown;
  try { payload = JSON.parse(text); }
  catch { throw new Error("Le fichier ne contient pas un profil JSON valide."); }
  const result = profileSchema.safeParse(payload);
  if (!result.success) throw new Error("Le profil Engine est invalide ou incompatible.");
  if (new Set(result.data.preferences.map(p => p.tag)).size !== result.data.preferences.length) throw new Error("Le profil contient des goûts en double.");
  return result.data;
}
const normalize = (s: string) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
type Candidate = {id: string; category: string; tags: string[]};
export type RecommendationKind = "personal" | "discovery";
/** Match first, then reserve half the slots for the Hub's remaining selection. */
export function mixRecommendations<T extends Candidate>(items: readonly T[], profile: EngineProfile | null) {
  const unique = [...new Map(items.map(item => [item.id, item])).values()];
  const kinds = new Map<string, RecommendationKind>();
  if (!profile || !profile.preferences.length) return {items: unique, kinds, personalCount: 0, target: 0};
  const weights = new Map(profile.preferences.map(p => [p.tag as string, p.weight]));
  const relevance = (item: T) => [...new Set([item.category, ...item.tags].map(normalize))].reduce((sum, tag) => sum + (weights.get(tag) || 0), 0);
  const target = Math.floor(unique.length / 2);
  const personal = unique.map((item, index) => ({item, index, score: relevance(item)}))
    .filter(entry => entry.score > 0).sort((a,b) => b.score - a.score || a.index - b.index).slice(0, target).map(entry => entry.item);
  const chosen = new Set(personal.map(item => item.id));
  const discovery = unique.filter(item => !chosen.has(item.id));
  const result: T[] = [];
  // Sparse matches fall back to discovery; they never acquire a fake personal badge.
  for (let i = 0; i < Math.max(personal.length, discovery.length); i++) {
    if (personal[i]) {result.push(personal[i]); kinds.set(personal[i].id, "personal");}
    if (discovery[i]) {result.push(discovery[i]); kinds.set(discovery[i].id, "discovery");}
  }
  return {items: result, kinds, personalCount: personal.length, target};
}

/** Describe the actual mix, including profiles without recognizable themes. */
export function recommendationSummary(total: number, personal: number, target: number, hasPreferences: boolean): string {
  if (!hasPreferences) return "Aucun thème reconnu dans ton profil · Sélection générale du Hub.";
  const counts = `${personal} pour toi · ${total - personal} découvertes`;
  if (personal < target) return `${counts} · Pas assez de correspondances pour atteindre 50 % avec cette sélection.`;
  if (total % 2) return `${counts} · Une découverte supplémentaire pour ce nombre impair de fonds.`;
  return `${counts} · Moitié goûts, moitié découverte.`;
}
