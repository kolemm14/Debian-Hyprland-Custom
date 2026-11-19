"use client";
import { useEffect, useRef, useState } from "react";
import { Monitor, X } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { parseEngineProfile, type EngineProfile } from "@/lib/recommendations";

export function EngineConnection({profile,onProfile}:{profile:EngineProfile|null;onProfile:(p:EngineProfile|null)=>void}) {
  const [open,setOpen] = useState(false);
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
  useEffect(() => {
    function receive() {
      const fragment = window.location.hash.slice(1);
      if (!fragment.startsWith("mpvp_profile=")) return;
      // Consume once; a fragment is never sent in an HTTP request.
      request.current++;
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
      try {
        if (fragment.length > 12500) throw new Error("Le profil Engine est trop volumineux.");
        onProfile(parseEngineProfile(decodeURIComponent(fragment.slice("mpvp_profile=".length))));
        toast.success("Ton profil Engine est chargé pour cette visite.");
      } catch {toast.error("Profil Engine incompatible. La sélection générale reste disponible.");}
    }
    receive(); window.addEventListener("hashchange", receive);
    return () => window.removeEventListener("hashchange", receive);
  },[onProfile]);
  async function importProfile(file:File|undefined) {
    if (!file) return;
    const current = ++request.current;
    try {
      if(file.size > 4096) throw new Error("Le profil doit faire moins de 4 Ko.");
      const parsed = parseEngineProfile(await file.text());
      if (current !== request.current) return;
      onProfile(parsed);setOpen(false);
      toast.success("Profil Engine chargé pour cette visite.");
    } catch(e) {if (current !== request.current) return; toast.error(e instanceof Error?e.message:"Profil invalide.");}
  }
  return <>
    <div className="engine-connection">
      <Monitor size={20}/><div><strong>{profile?"Profil MPVpaper Engine reçu":"Tes goûts MPVpaper Engine"}</strong><p>{profile?"Un mélange de tes goûts locaux et de découvertes du Hub, pour cette visite.":"Ouvre le Hub depuis Engine pour personnaliser la moitié des propositions."}</p></div>
      <button className="text-button" onClick={()=>setOpen(true)}>{profile?"Voir mes goûts":"Connecter Engine"}</button>
      {profile&&<button className="text-button" aria-label="Déconnecter le profil Engine" onClick={()=>{request.current++;onProfile(null);}}><X size={18}/></button>}
    </div>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="score-dialog"><DialogTitle>Tes goûts dans le Hub</DialogTitle><DialogDescription>Avec un profil Engine, la sélection vise 50 % de fonds proches de tes goûts et 50 % de découvertes. Les autres tris gardent leur classement habituel.</DialogDescription>
      {profile&&<><div className="taglist">{profile.preferences.map(p=><span key={p.tag}>#{p.tag}</span>)}</div><p>{profile.preferences.length?"Ces thèmes proviennent de ta bibliothèque, de tes favoris et des fonds déjà utilisés.":"Aucun thème reconnu dans ta bibliothèque : le Hub garde sa sélection générale."}</p></>}
      <p>Dans la version d’Engine avec la connexion Hub, ouvre <strong>Découvrir → Hub avec mes goûts</strong>. Un résumé de tes préférences est transmis uniquement à ce clic. Les chemins, les titres de fichiers et l’historique détaillé restent sur ton ordinateur.</p>
      <p>Tu peux aussi exporter le profil depuis Engine, puis l’importer ici :</p>
      <label className="secondary-button profile-import">Importer un profil JSON<input type="file" accept=".json,application/json" aria-label="Importer un profil Engine JSON" onChange={e=>{void importProfile(e.target.files?.[0]);e.target.value="";}}/></label>
      <p>Le profil reste dans cet onglet et disparaît au rechargement. Sans correspondance suffisante ou avec certains filtres, les places restantes servent à la découverte. Aucun compte Engine ni service local n’est nécessaire.</p>
    </DialogContent></Dialog>
  </>;
}
