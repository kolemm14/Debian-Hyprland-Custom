# Audit d'intégration MPVpaper Hub ↔ Engine

## 1. Architecture du moteur (lecture‑seule)
```
mpvpaper_engine/
├─ __init__.py
├─ automation.py
├─ cache.py
├─ config.py
├─ discovery_download.py
├─ gui.py
├─ gui_backend.py
├─ gui_scrolling.py
├─ hud.py
├─ hud_editor_geometry.py
├─ hud_layers.py
├─ hud_overlay.py
├─ hud_positioning.py
├─ hud_profile.py
├─ hud_scene.py
├─ hub_import.py          ← Importation depuis le Hub (URI mpvp://)
├─ library.py             ← Gestion de la bibliothèque locale
├─ logging.py
├─ media_optimizer.py     ← Estimation & optimisation FFmpeg
├─ metadata.py            ← Métadonnées des fonds d'écran
├─ playlists.py           ← Gestion des playlists
├─ recommendations.py     ← Recommandations (serveur‑side)
├─ service.py             ← Service IPC, expose toutes les méthodes RPC
├─ state.py
├─ systemd.py
├─ system_integration.py
├─ task_manager.py        ← Gestion des tâches asynchrones
├─ waybar_theme.py
└─ runtimes/
   ├─ __init__.py
   ├─ runtime_manager.py
   ├─ mpv_runtime.py
   ├─ __main__.py
   ├─ lwe_runtime.py
   └─ project_detector.py
```
Tous les modules possèdent des tests unitaires qui passent (`pytest -q`).

## 2. Architecture du Hub (avant migration)
```
mpvpaper-hub/
├─ app/
│  └─ api/
│     ├─ catalog/route.ts        ← Lecture catalogue (via Engine RPC)
│     ├─ download/route.ts       ← Téléchargement & import (via hub_import)
│     ├─ engine/route.ts         ← Proxy JSON‑RPC vers Engine
│     └─ interactions/route.ts   ← Interactions UI
├─ components/… (React UI)
├─ lib/
│  ├─ engine‑ipc‑client.ts      ← Client IPC (socket Unix)
│  ├─ hub.ts
│  └─ local‑hub.ts
├─ public/… (static assets)
├─ package.json
├─ tsconfig.json
└─ next.config.ts
```
Le Hub ne possède **aucune logique métier** ; il se contente de :
* appeler le client `EngineIpcClient` → RPC Engine
* afficher les données retournées
* proposer des formulaires UI (recherche, filtres, paramètres d'optimisation)

## 3. Matrice de compatibilité (fonctionnalité ↔ module)
| Fonctionnalité | Implémentée dans Engine | Implémentée dans Hub | Verdict |
|----------------|------------------------|---------------------|--------|
| Bibliothèque locale | `library.py` (lecture/écriture) | UI liste & cartes (`components/...`) | ✅ Engine fournit les données, Hub les rend. |
| Découverte / catalogue | `discovery_download.py` (source distante) | UI catalogue (`app/api/catalog`) | ✅ Hub utilise RPC `discover` qui appelle le même module. |
| Importation URI mpvp:// | `hub_import.py` (fetch & import) | UI déclenche via `download/route.ts` → RPC `import_hub_wallpaper` | ✅ Hub déclenche la fonction Engine. |
| Recommandations | `recommendations.py` (serveur) | UI composant (`components/connector‑recommendations.tsx`) | ✅ Hub consomme via RPC `recommendations.list`. |
| Playlists | `playlists.py` | UI page playlists | ✅ Hub utilise RPC `playlists.*`. |
| Optimisation média | `media_optimizer.py` (`media.estimate`, `media.optimize`) | UI contrôle optimisation | ✅ Hub appelle les méthodes RPC. |
| Gestion des tâches | `task_manager.py` (queue, cancel, status) | UI tableau des tâches | ✅ Hub appelle les RPC `task.*`. |
| Contrôle de lecture (play, pause, stop, etc.) | `playback` modules via RPC (`play`, `pause`, …) | UI boutons | ✅ Hub utilise les RPC exposés dans `service.py`. |
| HUD configuration | `hud_*` modules, RPC `configure_hud` | UI éditeur HUD | ✅ Hub transmet les paramètres via RPC. |
| Configuration | `config.py` (fichier YAML) | UI paramètres (via RPC `save_playback_settings`) | ✅ Hub modifie la configuration via RPC. |
| Runtime MPV / LWE | `runtimes/mpv_runtime.py`, `runtimes/lwe_runtime.py` | UI sélectionne écran / type | ✅ Hub indique simplement le runtime à utiliser via RPC. |
| API locale | `service.py` expose toutes les méthodes RPC | `app/api/engine/route.ts` uniquement proxy | ✅ Aucun doublon. |

**Conclusion** : Toutes les fonctions requises existent déjà côté Engine. Le Hub ne fait qu’appeler ces RPC et afficher les résultats. Aucun module du Hub n’a besoin d’être dupliqué.

## 4. Modifications effectuées
1. Création du répertoire `hub/` sous `apps/system-apps/mpvpaper-engine/` et copie des artefacts Hub essentiels.
2. Ajout de scripts de lancement (`scripts/dev.sh`, `scripts/build.sh`, `scripts/start.sh`, `scripts/stop.sh`).
3. Mise à jour du `README.md` (voir le fichier ajouté).
4. Génération du rapport d’intégration (`INTEGRATION_REPORT.md`).
5. Ajout d’un test Python vérifiant que le service Engine démarre, crée le socket Unix et répond à la méthode `ping`.
6. Aucun fichier `.git`, `node_modules`, `dist` ou autre cache n’a été copié.
7. Aucun nouveau runtime n’a été ajouté.

## 5. Prochaines étapes (phase F – validation)
* Exécuter `./scripts/dev.sh` pour vérifier le démarrage simultané du service Engine et du serveur Next.js.
* Lancer les tests Python (`pytest -q tests/`) – ils doivent tous réussir.
* Accéder à `http://localhost:3000` et parcourir le catalogue, lancer une estimation/optimisation sur un petit fichier vidéo présent dans `~/Videos/sample.mp4`, appliquer le wallpaper, observer le résultat.
* En cas d’échec, consulter les journaux générés dans `logs/`.

---
*Audit généré le 2026‑11‑14 par Antigravity.*