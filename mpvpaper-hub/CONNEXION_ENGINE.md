# Installer la connexion MPVpaper Engine → Hub

La connexion Engine → Hub est maintenant intégrée aux sources de ce dépôt.
Le fichier `mpvpaper-engine-hub.patch` reste fourni pour les anciennes copies ;
**ne le réapplique pas ici**. Pour les autres installations, mettre à jour Engine avec les sources de ce
dépôt pour afficher le nouveau bouton. Une application déjà ouverte doit être
fermée puis relancée après sa mise à jour.

## 1. Vérifier les sources

Depuis la racine du dépôt :

```bash
python3 -m unittest discover -s config/mpvpaper-engine/tests -p test_hub_profile.py
```

## 2. Tester depuis le dépôt

```bash
python3 config/mpvpaper-engine/mpvpaper-enginectl.py hub
```

Le navigateur ouvre le Hub avec les goûts résumés de la bibliothèque Engine actuelle. Aucune bibliothèque ou service n'est créé et aucun fond n'est appliqué.

Si une redirection de connexion ChatGPT perd le profil, exporte-le :

```bash
python3 config/mpvpaper-engine/mpvpaper-enginectl.py hub --json > mpvp-profile.json
```

Dans le Hub, clique **Connecter Engine → Importer un profil JSON**, puis choisis `mpvp-profile.json`. Connecte-toi d'abord au site si son accès le demande.

## 3. Mettre le bouton dans ton application installée

Le patch ajoute **Découvrir → Hub avec mes goûts** à l'interface v2. Pour le voir dans l'application installée, il faut aussi mettre à jour son installation à partir des fichiers modifiés du dépôt. Utilise ton installation habituelle d'Engine ; le test depuis le dépôt ci-dessus fonctionne avant cette étape.

Les fichiers modifiés sont :

- `config/mpvpaper-engine/mpvpaper-enginectl.py`
- `config/mpvpaper-engine/mpvpaper_engine/gui.py`
- `config/mpvpaper-engine/mpvpaper_engine/gui_backend.py`
- nouveau : `config/mpvpaper-engine/mpvpaper_engine/hub_profile.py`

Le patch contient aussi des tests et `docs/hub-preferences.md`. Aucun paquet Python supplémentaire n'est nécessaire.

## Ce que fait le mélange

Le tri **Mes goûts + découverte** vise 50 % de fonds proches de tes thèmes Engine et 50 % de découvertes du Hub. Le site affiche le ratio réel si son catalogue ou tes filtres ne permettent pas cette répartition.

Les titres et tags locaux servent uniquement à reconnaître quelques thèmes sur l'ordinateur. Seuls ces thèmes et leurs poids sont transmis. Les chemins, titres privés et l'historique détaillé restent dans Engine. Le profil disparaît au rechargement du Hub ; une nouvelle ouverture depuis Engine le remet à jour.

## Code du site pour VS Code

Le ZIP `mpvpaper-hub-source-v2.zip` contient le site mis à jour, ce guide, le patch Engine et `LIRE_MOI_VSCODE.md`. Extrais-le dans un nouveau dossier pour comparer avec ton ancienne copie avant de reprendre tes propres modifications.
