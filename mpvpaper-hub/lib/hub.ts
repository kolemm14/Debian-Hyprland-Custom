import { env } from "cloudflare:workers";
import catalogData from "@/data/catalog.json";
export type Wallpaper = {
 id:string;title:string;source:string;sourceUrl:string;author:string|null;authorRole:string|null;thumbnail:string;category:string;tags:string[];
 resolution:string|null;width:number|null;height:number|null;sizeMB:number|null;duration:number|null;
 type:"video"|"image"|"scene"|"web";downloadUrl:string|null;downloadMode:"direct"|"source"|"steam";
 checkedAt:string;sourcePolicy:string;sourcePolicyUrl:string;previewUrl:string|null;
};
export const wallpapers=catalogData as Wallpaper[];
export function database(){if(!env.DB)throw new Error("Database unavailable");return env.DB;}
export function findWallpaper(id:string){return wallpapers.find(w=>w.id===id);}
export const downloadHosts=new Set(["motionbgs.com","cdn.livelywallpaper.app","mylivewallpapers.com","moewalls.com","wallsflow.com"]);
export function validDownload(url:string){try{const u=new URL(url);return u.protocol==="https:"&&!u.username&&!u.password&&!u.port&&downloadHosts.has(u.hostname);}catch{return false;}}
export function sameOrigin(request:Request){return request.headers.get("origin")===new URL(request.url).origin;}
export function identity(request:Request){
 const user=request.headers.get("oai-authenticated-user-id");
 if(user&&request.headers.get("oai-authenticated-user-email"))return {id:"user:"+user,signedIn:true,cookie:null};
 const cookie=request.headers.get("cookie")?.match(/(?:^|;\s*)mpv_visitor=([a-f0-9-]{36})(?:;|$)/)?.[1];
 const id=cookie||crypto.randomUUID();return {id:"visitor:"+id,signedIn:false,cookie:cookie?null:"mpv_visitor="+id+"; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax"};
}
export function apiError(error:unknown){console.error("MPVpaper Hub storage error",error);return Response.json({error:"Les données sont momentanément indisponibles. Réessaie dans un instant."},{status:503});}
export async function recordEvent(userId:string,itemId:string,kind:"view"|"download_start"|"manifest"){
 await database().prepare("INSERT OR IGNORE INTO events (user_id,item_id,kind,day,created_at) VALUES (?,?,?,?,?)").bind(userId,itemId,kind,new Date().toISOString().slice(0,10),Date.now()).run();
}
export async function catalogFor(userId:string){
 const db=database();
 const [votes,eventRows,mine]=await Promise.all([
 db.prepare("SELECT item_id, SUM(favorite) favorites, COUNT(rating) votes, AVG(rating) average FROM interactions GROUP BY item_id").all(),
 db.prepare("SELECT item_id, SUM(kind='view') views, SUM(kind='download_start') downloads, SUM(kind='manifest') manifests, SUM(kind='download_start' AND day >= date('now','-7 days')) weekly FROM events GROUP BY item_id").all(),
 db.prepare("SELECT item_id, favorite, rating FROM interactions WHERE user_id=?").bind(userId).all()]);
 const v=new Map(votes.results.map((r:any)=>[r.item_id,r]));
 const e=new Map(eventRows.results.map((r:any)=>[r.item_id,r]));
 const m=new Map(mine.results.map((r:any)=>[r.item_id,r]));
 const rows=wallpapers.map(w=>({...w,favorites:0,votes:0,average:null,views:0,downloads:0,manifests:0,weekly:0,...v.get(w.id),...e.get(w.id),favorite:!!m.get(w.id)?.favorite,rating:m.get(w.id)?.rating??null}));
 const maxD=Math.max(1,...rows.map(w=>w.downloads)),maxF=Math.max(1,...rows.map(w=>w.favorites)),maxW=Math.max(1,...rows.map(w=>w.weekly));
 return rows.map(w=>({...w,score:w.votes+w.downloads+w.favorites===0?null:Math.round(100*(.5*((w.votes*(w.average||0)+30)/(w.votes+10)/5)+.25*Math.log1p(w.downloads)/Math.log1p(maxD)+.15*Math.log1p(w.favorites)/Math.log1p(maxF)+.1*w.weekly/maxW))}));
}
