# MPVpaper Hub intégré à « Découvrir »

Dans **Découvrir → MPVpaper Hub**, l’interface Hub s’ouvre dans la fenêtre Engine. La barre principale et la navigation restent celles d’Engine ; l’ancienne barre latérale Hub est masquée en mode intégré. L’onglet **Pour vous** réutilise séparément le classement local de MPVpaper Engine.

Le serveur Hub démarre à la première ouverture de l’onglet, écoute uniquement sur `127.0.0.1` avec un port éphémère et s’arrête quand la fenêtre Engine se ferme. Si les sources Hub ou les dépendances Node ne sont pas installées, les autres fonctions Engine restent disponibles. Les liens vers les fiches des sources s’ouvrent dans le navigateur par défaut.

La recherche interroge le catalogue MPVpaper, Wallhaven SFW et NASA Images ; l’état de chaque source apparaît sous la recherche. Les tendances et les mieux notés utilisent les statistiques Hub disponibles. La vue Nouveautés trie uniquement les dates de publication transmises par les sources et indique quand aucune date fiable n’est disponible.

Les images Wallhaven et les aperçus NASA importables sont téléchargés par le service Engine, enregistrés dans sa bibliothèque locale et indexés. Le contrat IPC `hub.v1.download` n’accepte que ces deux sources et leurs hôtes média enregistrés. Après téléchargement, **Appliquer le wallpaper** délègue à `hub.v1.apply`, qui ne peut appliquer qu’un média déjà indexé dans la bibliothèque Engine. Les favoris Hub externes deviennent des favoris Engine après import, afin d’éviter un deuxième stockage de favoris. Les autres fiches continuent d’utiliser les liens et modes de téléchargement propres à leur source.

Le service Hub ne démarre pas avec Engine. Les dépendances Node doivent être installées dans le dossier `apps/system-apps/mpvpaper-engine/hub` pour afficher le module intégré.

## Profil de goûts pour l’ancien lien web

La commande `mpvpaper-enginectl hub` reste disponible pour l’usage web externe. Elle lit un résumé local uniquement à son invocation et ouvre le navigateur par défaut.

Le Hub doit autoriser le compte utilisé dans le navigateur ; son propriétaire gère la visibilité. Si une connexion ou redirection perd le profil, utiliser l'import JSON ci-dessous.

```bash
mpvpaper-enginectl hub
mpvpaper-enginectl hub --json > mpvp-profile.json
```

Le deuxième appel n'ouvre pas de navigateur. Sur le Hub, choisir **Connecter Engine → Importer un profil JSON**. L'installation d'Engine doit inclure `mpvpaper_engine/hub_profile.py` ainsi que le contrôleur et l'interface mis à jour. Aucun paquet Python supplémentaire n'est nécessaire.

Le profil version 1 est envoyé dans le fragment `#mpvp_profile=` de l'URL, jamais dans la query string. Le Hub le retire de l'adresse et le garde uniquement pour la visite actuelle. Un rechargement efface le profil ; **Déconnecter le profil Engine** l'efface immédiatement.

## Préférences et confidentialité

- Lecture SQLite en mode `ro` et `query_only`, sans scan, migration ni création de bibliothèque.
- Au plus 1 000 fonds non manquants, favoris puis usages puis identifiant décroissant.
- Titres et tags analysés uniquement localement, par rapprochement de mots-clés publics. Aucun fichier média n'est analysé.
- Poids par fond : `1 + (4 si favori) + min(5, log2(1 + usage_count))`. Les poids cumulés par thème sont normalisés par leur maximum.
- Seuls 16 thèmes fixes et des poids de 0,01 à 1 sont transmis. Aucun chemin, titre local, nom d'utilisateur, identifiant, date, URL personnelle ni historique détaillé ne quitte Engine.
- Bibliothèque absente ou sans thème reconnu : profil vide, sélection générale du Hub. Base incompatible : erreur visible, sans modifier les données.

Le Hub vise une moitié de correspondances locales et une moitié de découvertes parmi son catalogue existant, après application des filtres. Un nombre impair ajoute une découverte. Les correspondances manquantes sont remplacées par des découvertes ; le ratio réel est affiché. Le score communautaire reste indépendant. Le navigateur ne détecte pas seul une application installée ou ouverte.

## Vérification

```bash
cd apps/system-apps/mpvpaper-engine
python3 -m unittest discover -s tests -p test_hub_profile.py -v
python3 -m compileall -q mpvpaper_engine/hub_profile.py mpvpaper_engine/gui.py mpvpaper_engine/gui_backend.py mpvpaper-enginectl.py
```

Les tests utilisent le schéma SQLite de production. Les clics GTK et l'ouverture du navigateur doivent aussi être vérifiés sur une session Linux avec GTK4/libadwaita.
