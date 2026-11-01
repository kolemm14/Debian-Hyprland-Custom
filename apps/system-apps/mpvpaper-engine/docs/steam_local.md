# Import depuis le client Steam

Dans Découvrir, ouvrez la fiche d’un élément Wallpaper Engine, puis cliquez
sur **Ouvrir dans Steam**. Connectez-vous dans le client Steam, abonnez-vous
au fond et vérifiez sa file de téléchargements. Wallpaper Engine et l’accès
au contenu doivent être disponibles sur ce compte ; l’abonnement seul ne
garantit pas le démarrage immédiat du téléchargement.

MPVpaper Engine vérifie les fichiers locaux toutes les trois secondes pendant
cinq minutes, puis arrête l’attente. **Annuler l’attente** arrête uniquement
cette vérification, pas le téléchargement Steam. Le bouton de téléchargement
sur une fiche Steam lance également cet import local, sans SteamCMD anonyme.
Les téléchargements depuis les autres sites conservent leur fonctionnement.

Les bibliothèques Steam natives, Flatpak, Snap et les emplacements supplémentaires
de `libraryfolders.vdf` sont recherchés. L’élément doit figurer dans
`WorkshopItemsInstalled` du manifeste `appworkshop_431960.acf`, avec la dernière
version connue et sans dossier de téléchargement en cours. Le `project.json`
et son fichier d’entrée sont validés. Un dossier apparu en cours de téléchargement
ou une image d’aperçu ne suffisent pas.

Les fichiers sont référencés sur place, sans copie ni modification dans Steam.
Video/Image utilisent le média original ; Scene/Web conservent le dossier complet.
Scene nécessite linux-wallpaperengine ; Web peut être enregistré mais son exécution
reste désactivée. Aucun fond n’est appliqué automatiquement après import.
Une désinstallation dans Steam peut donc rendre l’entrée indisponible.

Cette intégration ne transfère aucun cookie et ne lit aucun mot de passe ou fichier
d’authentification. Elle n’utilise pas le SDK Steamworks : le manifeste local est
un indicateur de disponibilité, pas une garantie de compatibilité du renderer.

Référence : [états des éléments Workshop dans Steamworks](https://partner.steamgames.com/doc/api/isteamugc#GetItemState).
