# Aurora Desktop Experience - Phase 0 Audit

## 1. Architecture Actuelle du Dépôt

Le projet `Debian-Hyprland-Custom` repose sur une structure d'installation modulaire :
- **Scripts de base (`core/`)** : Contient `setup.sh` (gestionnaire d'état XDG), `hardware.py`, `compatibility.py` (détection du profil matériel), et `i18n.sh` (internationalisation).
- **Configuration Hyprland (`config/hypr/`)** : Découpée en plusieurs sous-fichiers (`deblestia-ui.conf`, `deblestia-workspaces.conf`, `deblestia-input.conf`) avec des scripts de lancement et de gestion d'espace de travail.
- **Barres et interfaces** : Utilisation de configurations spécifiques pour Waybar (`config/waybar/configs/`), Nova Shell, Caelestia (Quickshell).
- **Manifestes (`manifests/`)** : Le fichier `components.tsv` gère probablement l'installation modulaire (components vs profils).
- **Système de test (`tests/`)** : Suite `pytest` validant l'installation dry-run et les dépendances.

## 2. Composants Réutilisables

Pour Aurora, nous pouvons et devons réutiliser les briques existantes sans les dupliquer :
- **Détection matérielle** : `core/hardware.py` et `core/compatibility.py` peuvent être étendus pour supporter les recommandations de profils Aurora (Lite, Balanced, Ultra).
- **Gestionnaire d'état** : `core/setup.sh` pour suivre l'installation d'Aurora et permettre un rollback propre.
- **Waybar / Rofi / Wallust** : Ils sont déjà intégrés dans l'écosystème du projet. Aurora fournira ses propres styles (fichiers dans `config/aurora/waybar` ou `config/waybar/configs/[Aurora]...`) au lieu de réinstaller ces paquets.
- **Composant UI (`hyprland.conf`)** : Utiliser la méthode `source = ~/.config/aurora/hypr/aurora.conf` pour activer Aurora de manière non destructive.

## 3. Risques Identifiés

- **Conflits de profils matériels** : Assurer que le basculement vers Aurora n'écrase pas brutalement un profil "Immersive" ou "Caelestia" actif sans sauvegarde préalable.
- **Performances** : Le moteur `aurora-performance` (gestion dynamique Lite/Balanced/Ultra) pourrait entrer en conflit avec les daemons existants (comme `hypridle`). Il devra être implémenté sous forme d'un script léger ou d'un service systemd-user isolé.
- **Dépendances** : Conserver la politique actuelle de `Debian-Hyprland-Custom` : aucune application lourde obligatoire.

## 4. Plan d'Intégration (Architecture Aurora adaptative)

Au lieu de créer un dossier racine complet `aurora/` qui casse la structure, nous allons intégrer Aurora proprement :
- **`config/aurora/hypr/`** : Configuration principale `aurora.conf`, `rules.conf`, `animations-lite.conf`, `animations-ultra.conf`.
- **`config/aurora/waybar/`** : Les barres Top Bar et Dock d'Aurora.
- **`config/aurora/rofi/`** : Aurora Spotlight.
- **`core/aurora-cli.sh` ou `bin/aurora`** : Le CLI pour gérer les profils et l'Eco mode.
- **`scripts/aurora/`** : Logique du moteur de performance et changement de profil à chaud (CLI de basculement).

Cette approche maintient le dépôt structuré et respecte le principe "Aurora est un environnement désactivable".
