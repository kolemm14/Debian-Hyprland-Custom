# Validation Steam Workshop dans Hyprland — 2026-09-29

Suite automatisée finale : **349 tests passent** (`python3 -m pytest -q
config/mpvpaper-engine/tests --tb=short`, hors sandbox pour les sockets Unix).
`git diff --check` et la compilation Python des modules modifiés passent.

La validation est **partielle** : la chaîne locale fonctionne dans une vraie
session Hyprland avec deux écrans physiques, mais les médias utilisés sont des
fixtures générées. Aucun contenu Workshop installé n’a été détecté dans les
bibliothèques Steam découvertes. Les téléchargements Steam et le redémarrage
complet de session ne sont pas validés.

| Contrôle | Résultat | Preuve / limite |
|---|---|---|
| ID → type VIDEO → original | PASS | Fixture 900000001, copie identique à l’original |
| ID → image originale | PASS | Fixture 900000002, copie identique à l’original |
| Lecture VIDEO et image | PASS | MPV IPC `path` et `video-params`, 640×360 |
| Deux écrans indépendants | PASS | VIDEO sur eDP-1, image sur HDMI-A-1 |
| Écrans physiques | Confirmés | LG Display interne et HP V213a HDMI, 1920×1080 chacun |
| Apply("*") | PASS | Vidéo décodée sur les deux sorties |
| Relance moteur + processus MPV | PASS | Fond commun restauré sur les deux sorties |
| Apply("*") puis choix individuel + relance | PASS | Image sur eDP-1, vidéo conservée sur HDMI-A-1 |
| Aperçu local/distant | Tests de régression | Aperçu déclaré et noms preview/thumb exclus ; URL d’aperçu non téléchargée |
| Vrais IDs Steam / téléchargement | À faire | Fournir deux contenus originaux installés localement |
| Logout/login Hyprland | À faire | Nécessite les changements installés et une reconnexion après sauvegarde du travail |
| Validation visuelle / transfert depuis autre fournisseur | À faire | Le test préserve les fournisseurs existants ; preuve actuelle par décodage IPC |

Le [rapport JSON](steam_workshop_session_report.json) contient les chemins et
paramètres MPV observés. Ses chemins `/tmp/mpv-we-*` étaient temporaires et ont
été supprimés après le test. Les unités de test sont distinctes du service
installé et arrêtées après chaque exécution. La configuration personnelle n’a
pas été déployée ou remplacée.

Des avertissements « MPV socket unavailable » apparaissent pendant la
reconstruction immédiate de l’état au démarrage des unités asynchrones. Les
vérifications attendent ensuite le socket et le décodage effectif ; toutes ont
réussi dans le délai de 15 secondes.

Corrections apportées : sélection commune du média entre import et résolveur,
prise en charge d’une image originale, rejet des previews déclarés et des liens
hors du dossier, refus d’annoncer une archive brute comme vidéo, suppression du
fallback d’import d’aperçu distant, rafraîchissement d’un média réimporté de même
taille, et persistance/restauration cohérente des choix globaux et individuels.

La sélection sans `project.json` reste une heuristique basée sur les extensions
et noms de fichiers. Les projets Scene/Web ne sont pas convertis en images de
prévisualisation. La validation finale doit utiliser les vrais projets visés.

Commandes reproductibles et procédure de reconnexion :
[guide de validation](steam_workshop.md#session-acceptance-test).
