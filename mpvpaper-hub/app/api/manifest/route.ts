import {findWallpaper,identity,recordEvent} from "@/lib/hub";
export async function GET(request:Request){
 const item=findWallpaper(new URL(request.url).searchParams.get("id")||"");
 if(!item)return Response.json({error:"Fond introuvable."},{status:404});
 try{await recordEvent(identity(request).id,item.id,"manifest");}catch(error){console.error("Manifest counter unavailable",error);}
 return Response.json({schema_version:1,mpvpaper_id:item.id,title:item.title,source:{name:item.source,url:item.sourceUrl,author:item.author},media:{type:item.type,url:item.downloadMode==="direct"?item.downloadUrl:null,resolution:item.resolution},policy:{mode:item.downloadMode,terms:item.sourcePolicyUrl},automatic_apply:false},{headers:{"Content-Disposition":'attachment; filename="'+item.id.replace(/[^a-z0-9-]/gi,"-")+'.mpvp.json"',"Cache-Control":"no-store"}});
}
