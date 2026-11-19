import {findWallpaper,identity,recordEvent,validDownload} from "@/lib/hub";
export async function GET(request:Request){
 const item=findWallpaper(new URL(request.url).searchParams.get("id")||"");
 if(!item)return Response.json({error:"Fond introuvable."},{status:404});
 if(item.downloadMode!=="direct"||!item.downloadUrl||!validDownload(item.downloadUrl))return Response.json({error:"Le téléchargement direct n’est pas disponible pour cette source.",sourceUrl:item.sourceUrl},{status:409});
 try{await recordEvent(identity(request).id,item.id,"download_start");}catch(error){console.error("Download counter unavailable",error);}
 return new Response(null,{status:302,headers:{Location:item.downloadUrl,"Cache-Control":"no-store","Referrer-Policy":"strict-origin-when-cross-origin"}});
}
