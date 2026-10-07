# Installation rapide

Sur Debian 13 avec GNOME, ouvrez un terminal :

```bash
git clone --depth 1 https://github.com/kolemm14/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./install.sh
```

Choisissez **Installation automatique**. Le diagnostic ne modifie rien. Avant
toute installation, Deblestia affiche le profil, les composants et les paquets,
puis demande une confirmation. GNOME et le gestionnaire de connexion existant
sont conservés.

Pour examiner la machine sans installer :

```bash
./install.sh diagnostic
```

Pour afficher aussi le profil, les composants et les dépendances sans demander
de confirmation et sans rien écrire : `./install.sh plan`.

Pour vérifier les mises à jour : `./update.sh --check`. Examinez ensuite
`./update.sh --dry-run`, puis lancez `./update.sh` depuis un checkout propre.
L’updater protège les personnalisations et met à jour uniquement les composants
installés. Voir le [guide de mise à jour](../UPDATER.md) et, pour un clone ancien
sans ce script, la [procédure de migration](../../README.md#mettre-à-jour-le-dépôt).
