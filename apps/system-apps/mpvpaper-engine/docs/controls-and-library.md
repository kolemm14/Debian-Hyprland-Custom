# Commandes et espaces de fichiers

La navigation sépare **Live · vidéos**, **Images**, **Scènes** et **Projets Web**.
Ce sont des vues de la bibliothèque : aucun fichier existant n’est déplacé ni
renommé. Recherche, favoris, application et corbeille continuent de fonctionner.
Les scènes demandent linux-wallpaperengine et ses ressources ; les projets Web
restent consultables mais leur exécution est bloquée par le moteur actuel.

Pause, reprise, arrêt, relance, volume, muet, vitesse, boucle, saturation et profil
concernent le **fond actif sur l’écran choisi**, pas simplement la vignette
sélectionnée. « Tous les écrans » envoie la commande à chaque écran connecté et
présente chaque résultat, y compris les erreurs ou commandes non prises en charge.
Les commandes utilisateur sont exécutées dans l’ordre.

« Enregistrer les réglages de lecture » mémorise volume, muet, vitesse, boucle et
profil de performance pour les prochaines lectures. Ce bouton ne capture pas de
vidéo de l’écran. Les changements de lecture ordinaires sont immédiats mais
l’enregistrement reste explicite. Le profil de performance choisi lors de
l’application d’un fond est transmis au moteur avant son lancement.

Le profil QUALITY concerne le rendu et les ressources ; la qualité 1080p/4K du
téléchargement dépend des formats disponibles chez la source et ne transforme pas
une vidéo basse résolution en haute résolution.

Vérifications : suite unittest du moteur, matrice des commandes et erreurs
multi-écrans, persistance/rejet des valeurs invalides, cible conservée pendant une
commande asynchrone, construction GTK4 des vues. Ces tests ne valident pas tous les
contenus distants ni un moteur de scènes absent. Les modifications apparaissent
à la prochaine ouverture de l’application déjà lancée.
