# Mise à jour incrémentale

Depuis un clone Git complet, en utilisateur normal :

```bash
./update.sh --check
./update.sh --dry-run
./update.sh
```

`update.sh` utilise Python 3 standard, Git et le verrou Linux `flock` via
`fcntl`. Il ne relance pas l’installation générale, ne change pas de profil de
bureau et ne recharge pas Hyprland de force. Debian 13 est la cible ; aucune
accélération graphique n’est nécessaire pour l’updater.

| Option | Effet |
|---|---|
| `--check` | Compare la référence installée à la branche distante, sans écriture persistante |
| `--dry-run` | Affiche Git A/M/D/R, destinations, suppressions, propositions `.new`, services, paquets et compilations ; ne compile ni n’installe |
| aucune | Applique les différences et répare les fichiers gérés manquants |
| `--force` | Restaure aussi les programmes gérés modifiés ; protège toujours les configurations, fichiers inconnus et médias |
| `--migrate-only` | Migre uniquement les anciens origins officiels reconnus |
| `--rollback` | Restaure la dernière transaction réussie, si aucun fichier concerné n’a été modifié depuis |
| `--yes` | Autorise les nouveaux paquets Debian affichés ; ne supprime aucun paquet |

Les clones partiels doivent inclure `core/update` et `manifests` :

```bash
git sparse-checkout add core/update manifests
```

Les origins officiels historiques HTTPS, SSH SCP et SSH URI sont reconnus par
égalité exacte. Le protocole est conservé. Les forks, hôtes personnalisés,
origins multiples et URLs de push explicites ne sont pas réécrits. La branche
suivie sur `origin` est utilisée ; sans tracking, la cible est `main`. Les
historiques divergents ne sont jamais fusionnés automatiquement. La vérification
et le dry-run récupèrent les objets dans un dépôt temporaire, sans changer les
refs, `FETCH_HEAD` ou le remote du clone utilisateur.

## Audit des installateurs et périmètre

Le fichier `manifests/components.tsv` et l’état historique
`${XDG_STATE_HOME:-~/.local/state}/deblestia/setup/components` restent les
références des composants. `manifests/update-files.json` décrit leurs destinations
et politiques par fichier. Il ne signifie pas que tous ces composants sont
installés.

| Installateur | Destinations réellement utilisées | Traitement de l’updater |
|---|---|---|
| `install.sh`, `core/setup.sh` | État `deblestia/setup`, profil et composants choisis | Réutilisés, jamais réinitialisés |
| `install-nova2.sh` et wrappers Bar/Nova Lite/Nova 2 | `$XDG_CONFIG_HOME/waybar`, `hypr/scripts`, `hypr/UserScripts`, includes Hyprland ; sélection dans `deblestia/ui-mode` | Scripts/assets suivis, configs protégées, sélection active conservée |
| `install-v2.sh` / Deblestia Shell | `caelestia/shell.json`, includes/scripts Hyprland, état `debian-immersive-v2`, thèmes téléchargés | Les sept fichiers copiés sont suivis ; thèmes, profil et réglages restent personnels |
| `install-nova-shell.sh` | `quickshell/deblestia-nova`, includes/scripts, `illogical-impulse/config.json`, backups Nova | Wrappers et réglages locaux suivis ; patches QML reconstruits sur le HEAD amont déjà installé |
| `install-mpvpaper-engine.sh` | `~/.local/lib/mpvpaper-engine`, six liens dans `~/.local/bin`, `.desktop` dans `~/.local/share/applications`, trois unités dans `~/.config/systemd/user` | Programme/modules/launchers/unités mis à jour, tests inclus ; configuration et bibliothèques exclues |
| `install-v3.sh` / PeriphX | `~/.local/lib/debian-next-v3`, liens `periphx`, alias historique, CLI, `pericored`, desktop, unité `$XDG_CONFIG_HOME/systemd/user` | Programme, launcher généré et binaire Rust suivis ; données utilisateur exclues |
| `install-mirrorbridge.sh` | Binaire `~/.local/bin/mirrorbridge`, desktop utilisateur | Compilation différentielle puis remplacement transactionnel |
| `install-aurora.sh` | Lien `~/.local/bin/aurora` vers le clone ; état/profil généré dans `~/.config/aurora` | Lien suivi, code du clone avancé ; choix et profil généré conservés |
| Helpers SDDM et `install-v2.sh pam-fix` | `/usr/share/sddm/themes/simple_sddm_2`, `/etc/tmpfiles.d/deblestia-caelestia-faillock.conf` | Opérations administrateur explicites hors mise à jour utilisateur |

Les installateurs audités ne déploient pas les programmes de ce projet dans
`/usr/local/bin` ou `/usr/share/applications`. Les composants tiers et paquets
système restent sous leur propre gestion. Les modifications `PATH` de PeriphX,
les sources de `hyprland.conf`, les couleurs générées et les sélections Waybar
ne sont pas réinsérées par l’updater. Il ne crée donc pas de nouvelles lignes
`exec-once`, `bind`, `env`, `source`, alias, règles udev ou polkit.

Les anciens scripts conservent leurs conventions : certains chemins sont
historiquement fixés à `$HOME/.local` ou `$HOME/.config`, d’autres respectent
XDG. Le mapping reproduit ces différences sans déplacer l’installation.

## Manifest, version et propriété

État, avec les valeurs XDG usuelles :

```text
~/.local/share/debian-hyprland-custom/installed-files.json
~/.local/share/debian-hyprland-custom/version
~/.local/share/debian-hyprland-custom/backups/<date>-<identifiant>/journal.json
~/.local/state/debian-hyprland-custom/update.log
~/.local/state/debian-hyprland-custom/update.lock
~/.local/state/debian-hyprland-custom/pending.json
```

Le manifest JSON versionné contient uniquement les fichiers adoptés/installés,
leur destination, composant, source, commit, politique, contenu de référence,
permissions et type (fichier ou lien). Les références sont embarquées pour
permettre comparaison, restauration et réparation hors compilation. Les binaires
compilés enregistrent aussi l’empreinte de leurs sources. Le manifest et la
version ne changent qu’après vérification complète d’une mise à jour. Une
installation initiale réussie enregistre séparément ses fichiers réels.

Les installateurs appellent `core/update/record.sh` après leur réussite. Les
restaurations/désinstallations disponibles retirent le composant du suivi et
l’excluent des détections historiques jusqu’à sa réinstallation. Les composants
non choisis ne sont jamais installés par le simple ajout d’un mapping.

Pour une installation antérieure au manifest, les traces des installateurs et
les chemins corroborés identifient les composants. Seuls les fichiers exactement
identiques à la référence peuvent être adoptés automatiquement. Une version
installée ancienne ne peut pas être devinée de façon certaine : en l’absence
de manifest, HEAD sert de référence de comparaison et les différences sont
conservées. Un binaire historique sans preuve de provenance peut recevoir une
proposition `.new`, plutôt qu’un remplacement aveugle.

## Personnalisations et suppressions

- Fichier identique à sa référence : remplacement atomique par la nouvelle version.
- Configuration ou fichier inconnu modifié : original conservé, nouvelle version
  déposée en `.new`. Si ce nom appartient déjà à l’utilisateur, un suffixe
  d’empreinte évite de l’écraser. Un nouveau lancement ne multiplie pas les propositions.
- Programme géré modifié : même protection par défaut ; `--force` permet sa réparation.
- Suppression/renommage : l’ancienne destination est retirée uniquement si elle
  est encore identique à sa référence. Un ancien fichier personnalisé est conservé
  et signalé. Les ajouts précèdent les suppressions.
- Liens : le lien lui-même est remplacé, jamais sa cible. Les parents symboliques
  non pris en charge sont refusés pour éviter une écriture hors périmètre.

Aucun merge textuel spéculatif n’est effectué. Après vérification manuelle,
remplacez votre configuration par la proposition fusionnée. L’updater enlève
une proposition dont le contenu a été adopté exactement, s’il peut toujours
prouver qu’il en est propriétaire.

## MPVpaper, Nova, compilations et services

Les médias importés, bases de bibliothèque, choix par écran, `config.json`,
playlists, historique, environnement privé `.venv` et données runtime MPVpaper
ne figurent pas dans les mappings. Ils ne sont ni remplacés ni sauvegardés comme
fichiers de programme. Les fichiers de test ajoutés se trouvent dans le dossier
du programme, pas dans la bibliothèque de médias.

Pour Nova, les patches locaux sont appliqués dans un dossier temporaire à la
référence Git amont installée. Les modifications QML personnelles suivent la
politique `.new`. La suppression d’un patch restaure la référence amont des
fichiers déjà suivis. Le shell tiers lui-même n’est pas téléchargé à nouveau ;
son changement de version reste la fonction explicite de l’installateur Nova.
Une référence amont absente ou un patch incompatible bloque la transaction.

PeriphX/MirrorBridge sont compilés avec `cargo build --release --locked` seulement
si les sources ont changé ou si aucune référence exploitable n’existe. Un binaire
manquant peut être réparé depuis le manifest sans recompiler. Le dry-run annonce
le fichier à compiler, sans prétendre connaître ses octets futurs. Rust et les
bibliothèques de développement du composant doivent être disponibles. Un échec
ou timeout de compilation survient avant toute modification des programmes installés.

Les dépendances supplémentaires se déclarent dans la clé `packages` du manifest
de destinations, par composant. Seules celles des composants présents sont
vérifiées par `dpkg-query`. Apt n’est appelé que si elles manquent et après
confirmation, ou avec `--yes`. Aucune suppression automatique de paquet.

L’updater mémorise l’état actif/activé des unités concernées, arrête celles qui
étaient actives, recharge systemd si une unité change et redémarre uniquement
ce qui tournait. Une unité renommée est reliée à l’ancienne par la preuve de
renommage Git ; son état activé est transféré. Une unité nouvellement ajoutée
n’est pas activée silencieusement. Si le bus utilisateur est absent, le besoin
de rechargement est enregistré pour la prochaine exécution en session.

Les processus graphiques lancés manuellement ne sont pas tués : une fenêtre
MPVpaper ou un shell Quickshell déjà ouvert peut nécessiter une relance manuelle
pour charger tout son nouveau code. `hyprctl monitors` et `hyprctl clients`
servent de vérification non bloquante ; leur absence hors session n’est pas une erreur.

## Transaction et récupération

1. Verrou exclusif, contrôle du checkout et récupération d’un journal interrompu.
2. Fetch isolé, comparaison des commits, inspection A/M/D/R et préparation.
3. Validation Python/shell, calcul des conflits et des dépendances ; compilation si nécessaire.
4. Sauvegarde durable des seuls fichiers concernés, du manifest et de la version.
5. Arrêt ciblé, remplacements atomiques, suppressions prouvées, vérification des octets.
6. Rechargement/reprise des services, avance Git uniquement en fast-forward.
7. Écriture du manifest/version, puis marquage de la transaction comme réussie.

Les cinq dernières sauvegardes terminées sont conservées. Le journal pending
est durable avant la première modification : SIGTERM/exception déclenche un
rollback ; après SIGKILL, la prochaine exécution récupère le journal. Le rollback
refuse d’écraser une modification utilisateur survenue depuis la transaction.
En cas de restauration impossible, le journal est conservé pour intervention.

Les ajouts de paquets apt et le cache Cargo ne sont pas désinstallés en rollback.
Les scripts de hooks Git personnels ne font pas partie de la transaction.
Le checkout doit être propre avant application ; il n’est jamais stashed ni
réinitialisé de force. Le rollback Git utilise `reset --keep` uniquement si HEAD
est encore le commit de la transaction et si le checkout est resté propre.

## Étendre les mappings

Les nouvelles sources à l’intérieur d’un glob géré sont installées pour les seuls
composants présents. Une nouvelle destination ou un fichier généré doit avoir
une recette explicite et testée dans `manifests/update-files.json`. Ne pas mapper
les répertoires de données personnelles ni élargir un glob à tout `~/.config`.
Les patches et opérations système nécessitant root restent des actions distinctes.

## Validation

```bash
bash -n update.sh
bash -n install.sh
./contribute.sh test
python3 -m unittest discover -s config/mpvpaper-engine/tests -v
python3 -m unittest discover -s config/v3/tests -v
```

Les tests updater utilisent de vrais dépôts Git temporaires et un HOME isolé.
Les appels systemd et la compilation sont simulés pour ne pas arrêter les
services du développeur. Ils couvrent répétitions deux/cinq fois, reset partiel,
ajout/modification/suppression/renommage, liens, `.new`, rollback, journal
interrompu, versions, verrou, composants optionnels, MPVpaper, unités renommées,
paquets, dry-run sans écriture et patches Nova.
