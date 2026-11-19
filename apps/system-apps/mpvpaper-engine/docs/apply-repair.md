# Correctif d'application des fonds — 9 octobre 2026

Les journaux contenaient des échecs répétés : `Stop the legacy wildcard wallpaper
before using per-screen runtimes`. Le gestionnaire refusait chaque écran d'une
application globale lorsqu'un ancien lecteur partagé détenait encore le bureau.

`RuntimeManager.apply_all(path)` valide maintenant le média et le moteur avant
l'arrêt contrôlé de ce lecteur partagé, puis applique le fond aux écrans
connectés, sous le verrou existant. Un remplacement limité à un écran reste
protégé pour ne pas effacer implicitement le fond des autres écrans ; le message
explique de choisir d'abord « Tous les écrans ». Une source invalide laisse
l'ancien lecteur en place.

Le backend graphique remonte un échec explicite lorsqu'aucun écran n'a accepté
le fond. Il n'enregistre alors ni faux choix de fond ni entrée d'historique.
Une sélection effectivement enregistrée réactive `enabled` avec `autostart`.

Validation exécutée :

```sh
python3 -m pytest apps/system-apps/mpvpaper-engine/tests/test_runtimes.py \
  apps/system-apps/mpvpaper-engine/tests/test_gui_backend.py \
  apps/system-apps/mpvpaper-engine/tests/test_service.py -q
```

**61 tests réussis**, dont migration globale, conservation du lecteur si le
nouveau fond est invalide et absence de faux succès/historique en cas d'échec.

Les deux fichiers `runtimes/runtime_manager.py` et `gui_backend.py` ont été copiés
dans l'installation locale après sauvegarde dans
`~/.local/state/mpvpaper-engine/backups/apply-fix-20261009-143845`.
Le service a été redémarré. La configuration actuelle avait entre-temps évolué :
le fond sélectionné est « Denia Cosmic Wuthering Waves », et non l'ancien choix
partagé Frieren. Le choix courant a été conservé. Une demande d'application sur
eDP-1 a renvoyé `unchanged`, le lecteur actif correspondant déjà au fond demandé.
La propriété MPV `path` confirme le fichier et `time-pos` indique la lecture.
Le service Engine et son lecteur eDP-1 sont tous deux actifs.
