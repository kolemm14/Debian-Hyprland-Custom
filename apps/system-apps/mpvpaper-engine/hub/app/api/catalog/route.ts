import {catalogFor,identity,wallpapers} from "@/lib/hub";
export async function GET(request:Request){
 const user=identity(request),headers={"Cache-Control":"private, no-store",...(user.cookie?{"Set-Cookie":user.cookie}:{})};
 try{return Response.json({items:await catalogFor(user.id),signedIn:user.signedIn,statsAvailable:true},{headers});}
 catch(error){console.error("Catalogue statistics unavailable",error);return Response.json({items:wallpapers.map(w=>({...w,favorites:0,votes:0,average:null,views:0,downloads:0,weekly:0,score:null,favorite:false,rating:null})),signedIn:user.signedIn,statsAvailable:false},{headers});}
}
