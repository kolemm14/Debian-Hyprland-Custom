import {identity,sameOrigin,database,findWallpaper,apiError,recordEvent} from "@/lib/hub";
import {z} from "zod";
const inputSchema=z.object({id:z.string().min(1).max(200),action:z.enum(["view","favorite","rating"]),value:z.union([z.boolean(),z.number()]).optional()}).strict();
export async function POST(request:Request){
 if(!sameOrigin(request))return Response.json({error:"Origine invalide."},{status:403});
 if(Number(request.headers.get("content-length")||0)>2048)return new Response(null,{status:413});
 try{
 const raw=await request.text();
 if(raw.length>2048)return Response.json({error:"Requête trop volumineuse."},{status:413});
 const parsed=inputSchema.safeParse(JSON.parse(raw));
 if(!parsed.success)return Response.json({error:"Requête invalide."},{status:400});
 const body=parsed.data,user=identity(request);
 if(!findWallpaper(body.id))return Response.json({error:"Fond introuvable."},{status:404});
 if(body.action==="view"){await recordEvent(user.id,body.id,"view");return Response.json({ok:true},{headers:user.cookie?{"Set-Cookie":user.cookie}:{}});}
 if(!user.signedIn)return Response.json({error:"Connecte-toi pour enregistrer tes favoris et ta note."},{status:401});
 if(body.action==="favorite"&&typeof body.value==="boolean"){
 await database().prepare("INSERT INTO interactions (user_id,item_id,favorite,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET favorite=excluded.favorite,updated_at=excluded.updated_at").bind(user.id,body.id,body.value?1:0,Date.now()).run();
 }else if(body.action==="rating"&&typeof body.value==="number"&&Number.isInteger(body.value)&&body.value>=1&&body.value<=5){
 await database().prepare("INSERT INTO interactions (user_id,item_id,rating,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET rating=excluded.rating,updated_at=excluded.updated_at").bind(user.id,body.id,body.value,Date.now()).run();
 }else return Response.json({error:"Action invalide."},{status:400});
 return Response.json({ok:true});
 }catch(error){if(error instanceof SyntaxError)return Response.json({error:"Requête invalide."},{status:400});return apiError(error);}
}
