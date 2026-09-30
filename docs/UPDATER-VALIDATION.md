# Update system — rapport du 29 septembre 2026

## Files created

- `core/update/main.py` : orchestration, fetch temporaire, commits, CLI, dépendances.
- `core/update/files.py` : mappings, références, plan différentiel, validation et écritures atomiques.
- `core/update/transaction.py` : verrou, sauvegardes, journal durable, rollback et systemd.
- `core/update/patches.py` : reconstruction des patches Nova hors de l’installation active.
- `core/update/record.sh` : enregistrement après installation réussie.
- `manifests/update-files.json` : destinations auditées, politiques et services par composant.
- `tests/test_update_system.py` : transactions et scénarios d’installation/mise à jour isolés.
- `docs/UPDATER.md` et ce rapport.

## Files modified

`update.sh` remplace le précédent simple pull par le point d’entrée de l’updater.
Les installateurs `install-mpvpaper-engine.sh`, `install-nova2.sh`,
`install-v2.sh`, `install-v3.sh`, `install-nova-shell.sh`,
`install-mirrorbridge.sh` et `install-aurora.sh` enregistrent leurs fichiers après
succès ; les restaurations disponibles retirent le composant du suivi.

`tests/test_repository_update.py` réutilise le nouveau point d’entrée dans ses
clones isolés. Les README FR/EN et `docs/installation/QUICKSTART.md` décrivent les
nouveaux modes et les exigences des clones partiels.

Les changements préexistants de Steam Workshop, profils matériels, Aurora et
installation unifiée ne sont pas réécrits par cette tâche. `manifests/components.tsv`
conserve la sélection de composants existante.

## Manifest

`${XDG_DATA_HOME:-~/.local/share}/debian-hyprland-custom/installed-files.json`.
Chaque destination suivie contient son composant, source, commit, politique,
référence, permissions et contenu installé. `version` conserve le commit et la
branche. Les versions inconnues des installations historiques sont affichées
comme inconnues ; HEAD sert uniquement de référence prudente d’adoption.

## Backup

Sous `debian-hyprland-custom/backups/`, journal privé par transaction ; rétention
des cinq dernières sauvegardes terminées. Seuls les fichiers concernés et les
métadonnées sont sauvegardés. Les vidéos/bibliothèques utilisateur sont exclues.

## Rollback

Rollback automatique sur erreur/SIGTERM ; récupération du journal au lancement
suivant après SIGKILL. `--rollback` restaure la dernière transaction réussie.
Une modification utilisateur ultérieure bloque sa restauration destructive.
Les tests incluent de vrais SIGTERM et SIGKILL envoyés au processus updater.

## Remote migration

Anciennes origines officielles HTTPS/SSH reconnues exactement ; protocole
conservé. Les remotes personnalisés et URLs de push explicites restent intacts.
La branche suivie est respectée, avec `main` comme défaut sans tracking.
Les modes check/dry-run ne modifient ni remote ni refs du checkout.

## Duplicate prevention

Comparaison des références et destinations, aucune réexécution des installateurs,
aucun append de configuration. Renommages : nouveau fichier d’abord, suppression
prouvée ensuite. Tests deux/cinq exécutions, liens manquants, reset partiel puis
réparation, conservation du mtime du manifest lors d’une seconde mise à jour
sans changement, et nettoyage des propositions devenues obsolètes.

## User config preservation

Configs modifiées conservées avec `.new`, collision d’un `.new` personnel évitée,
pas de merge textuel aveugle. `--force` ne remplace que des programmes déjà suivis,
sans changement de type fichier/lien ; les médias et configurations restent protégés.
Un ancien fichier supprimé/renommé mais personnalisé reste conservé et signalé.

## MPVpaper Engine

Mise à jour ciblée du programme, modules, tests, liens, desktop, service et timer.
Tests de conservation des réglages par écran, médias et base de bibliothèque.
L’absence de MPVpaper ne provoque aucune installation ni activation de service.

## Systemd

Validation structurelle des unités avant application, arrêt/reprise des seules
unités concernées auparavant actives. Daemon-reload sur changement d’unité,
transfert d’activation lors d’un renommage Git reconnu. Absence de bus : reprise
différée signalée. Les transitions systemd sont simulées dans les tests ; aucun
service de la session du développeur n’a été arrêté par ces essais.

## Dry-run

Exécuté avec succès sur l’installation réelle, en lecture seule. Le plan signale
les personnalisations existantes et les compilations PeriphX/MirrorBridge.
Des tests comparent aussi les contenus du HOME et de `.git` avant/après pour
prouver l’absence d’écriture persistante. Les octets d’un binaire à compiler ne
sont pas inventés : sa destination et la compilation requise sont annoncées.

## Check mode

Exécuté avec succès sur le dépôt réel. Référence locale : `06ff80c64a81`, distante
sur `main` : `0c2002204f2e`. Faute de manifest historique, la version réellement
installée est explicitement inconnue. Aucune application sur ce checkout modifié.

## Tests

- `bash -n update.sh`, `bash -n install.sh` et les 50 scripts shell : succès.
- `./contribute.sh test` : 56 tests du socle et de l’updater + 349 tests MPVpaper, tous réussis.
- Suite V3/PeriphX : 20 tests réussis. Total : **425 tests réussis**.
- Compilation syntaxique des modules updater et `git diff --check` : succès.
- Dépôts Git temporaires réels ; systemd et construction Cargo simulés.
- Les appels `--check` et `--dry-run` réels réussissent sans appliquer le plan.

## Remaining risks

- La mise à jour réelle de cette installation n’a pas été appliquée : le checkout
  contient des modifications non commitées, que l’updater refuse d’écraser.
- Les fenêtres GUI et shells tiers déjà ouverts peuvent nécessiter une relance
  manuelle pour charger tous leurs nouveaux modules. Hyprland n’est pas redémarré.
- Les fichiers historiques sans preuve de propriété, notamment les binaires,
  sont conservés ; une proposition `.new` peut demander une décision manuelle.
- Les compilations réelles exigent les toolchains/bibliothèques du composant.
  Un échec de build bloque l’application. Les paquets ajoutés et caches Cargo
  ne sont pas désinstallés en rollback.
- Les opérations SDDM/PAM système restent manuelles. Les patches Nova exigent
  la référence Git amont installée et doivent toujours s’y appliquer proprement.
- Une nouvelle destination doit être déclarée dans le manifest audité ; il n’y
  a volontairement aucune copie globale de `config/` dans les données utilisateur.

Les logs de validation de cette session sont sous `/tmp/updater-release-check.log`,
`/tmp/updater-v3-final.log`, `/tmp/updater-final-check.log` et
`/tmp/updater-final-live-dry-run.log` ; ce rapport conserve les résultats utiles
après expiration des fichiers temporaires.
