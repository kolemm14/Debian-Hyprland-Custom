# MPVpaper Engine

MPVpaper Engine est une application de bureau Linux pour gérer une bibliothèque
locale de fonds vidéo et images, les appliquer aux écrans et contrôler la
lecture. L’interface GTK fonctionne sans MPVpaper Hub; le Hub web local est une
interface complémentaire qui nécessite Node.js.

## Télécharger et installer

Le workflow de release publie le paquet Debian de l’installateur central, pas un
paquet autonome de MPVpaper Engine. Téléchargez les sources de l’application
avec un clone partiel du dépôt :

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/kolemm14/Debian-Hyprland-Custom.git mpvpaper-engine
cd mpvpaper-engine
git sparse-checkout set install-mpvpaper-engine.sh update.sh core/update manifests \
  apps/system-apps/mpvpaper-engine
./install-mpvpaper-engine.sh check
./install-mpvpaper-engine.sh install
```

L’action `check` liste les dépendances système manquantes avant l’installation.
Après installation, lancez l’application avec :

```bash
mpvpaper-engine
```

L’installateur place Engine dans `~/.local/lib/mpvpaper-engine`, crée les
commandes dans `~/.local/bin`, installe le service utilisateur systemd et
conserve une sauvegarde avant remplacement. Pour retirer Engine et restaurer
les fichiers suivis par l’installateur :

```bash
./install-mpvpaper-engine.sh restore
```

Gardez le clone partiel pour les mises à jour et la restauration. Il contient
`update.sh` et les règles de propriété nécessaires à ces opérations.

## Activer MPVpaper Hub

L’installateur copie les sources du Hub avec Engine. Les dépendances Node ne
sont pas installées automatiquement. Pour activer l’interface web intégrée,
installez Node.js **22.13 ou plus récent**, activez pnpm **11.25.0**, puis
construisez le Hub installé :

```bash
npm install --global pnpm@11.25.0
cd ~/.local/lib/mpvpaper-engine/hub
bash scripts/install-pnpm.sh
pnpm build
```

Ouvrez ensuite MPVpaper Engine et choisissez **Découvrir**. La fenêtre embarquée
démarre le Hub sur une adresse loopback privée. Pour utiliser le Hub en mode
développement depuis le clone :

```bash
systemctl --user start mpvpaper-engine.service
cd apps/system-apps/mpvpaper-engine
./scripts/dev.sh
```

`./scripts/build.sh` construit la version locale. Après construction,
`./scripts/start.sh` lance le Hub précompilé; `./scripts/stop.sh` arrête
uniquement ce Hub. Le service Engine reste géré par systemd.

## Fonctions

- Bibliothèque locale avec favoris, playlists, historique et filtres.
- Fonds vidéo appliqués par écran avec contrôles de lecture.
- Téléchargement yt-dlp avec limite de résolution, reprise et fragments
  parallèles pour les sources HLS/DASH.
- Téléchargements Hub suivis par progression et annulables avant leur import
  final dans la bibliothèque.
- Runtimes MPVpaper et Linux Wallpaper Engine, selon leur disponibilité locale.
- HUD de bureau optionnel et intégration de thème.
- Service local protégé par socket Unix et pont HTTP limité à `127.0.0.1`.

Le Hub nécessite Internet pour rechercher ou télécharger certaines sources.
L’usage de ces publications reste soumis aux conditions des sites d’origine.

## Tests et développement

Depuis la racine du dépôt :

```bash
python3 -m unittest discover -s apps/system-apps/mpvpaper-engine/tests
```

Pour tester le Hub :

```bash
cd apps/system-apps/mpvpaper-engine/hub
npm test
npx tsc --noEmit
```

## Arborescence

```text
apps/system-apps/mpvpaper-engine/
├── mpvpaper_engine/   # service, IPC, bibliothèque et téléchargement
├── hub/               # application web locale et son runtime
├── scripts/           # démarrage, construction et développement du Hub
├── tests/             # tests Python du moteur et de ses intégrations
├── manifest.yaml      # cycle d’installation et métadonnées
└── README.md
```

Le Hub web communautaire publié séparément se trouve dans
[`mpvpaper-hub/`](../../../mpvpaper-hub/README.md); il n’est pas requis pour
appliquer des fonds depuis la bibliothèque locale.
