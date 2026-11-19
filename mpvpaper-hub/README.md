# MPVpaper Hub

Catalogue de fonds d’écran pour Linux, construit pour Kolemm14. Les crédits et la provenance sont conservés. Les fichiers ne sont pas réhébergés.

## Ce qui fonctionne

- Catalogue de 12 publications réelles, vérifiées le 7 octobre 2026 : MotionBGS, LivelyWallpaper.app, MyLiveWallpapers, MoeWalls, Wallsflow et Backiee.
- Connexion explicite depuis MPVpaper Engine : profil agrégé local, mélange visant 50 % de goûts et 50 % de découverte. Le ratio réel est affiché ; aucun profil n’est envoyé aux API du Hub.
- Recherche, catégories, source, résolution, filtres pour PC modeste, téléchargement direct et tris.
- Quatre liens MP4 publics vérifiés : deux MotionBGS, deux LivelyWallpaper.app. Le bouton du Hub redirige vers le fichier officiel. Les autres fiches ouvrent le parcours de téléchargement de leur source.
- Aperçu vidéo à la demande, sans lecture continue dans le catalogue.
- Favoris et notes durables dans D1, associés à l’identité transmise par la plateforme Sites. Connexion ChatGPT pour voter et enregistrer des favoris.
- Compteurs du Hub distincts des statistiques des sources. Un lancement de téléchargement n’est pas présenté comme un téléchargement terminé.
- Une note par compte, modifiable. Un événement par visiteur, fond, type et jour.
- Score commun : notes bayésiennes 50 %, lancements logarithmiques normalisés 25 %, favoris logarithmiques normalisés 15 %, lancements récents sur 7 jours 10 %. Aucune activité = aucun score.
- Export `.mpvp.json` conservant la provenance et `automatic_apply: false`.
- Interface française, responsive, navigation clavier, composants de dialogue accessibles et réduction des animations.

## Utilisation

1. Ouvrir une fiche dans le Hub.
2. Cliquer **Télécharger** lorsqu’un lien direct existe, ou **Télécharger sur la source** pour suivre son parcours original.
3. Importer le fichier MP4 ou l’image dans MPVpaper Engine.
4. Choisir l’écran et appliquer le fond dans le client Linux.
5. Se connecter pour enregistrer un favori ou attribuer une note.

## Limites de cette première version

Le catalogue est une sélection vérifiée ; il ne prétend pas contenir l’ensemble des catalogues sources. Il n’effectue pas encore d’aspiration régulière de leurs publications. Aucun scraper ne contourne les étapes publicitaires, comptes ou restrictions. Les capacités de chaque fiche sont explicites. Les champs inconnus restent inconnus.

L’import automatique du fichier JSON nécessite un adaptateur dans MPVpaper Engine. Aucun gestionnaire du protocole `mpvp://` n’est supposé installé. Steam local et VSThemes apparaissent comme sources à connecter ; aucune intégration fonctionnelle n’est simulée. Pinterest n’est pas indexé. La durée d’utilisation, les installations réelles et les performances CPU/GPU ne sont pas collectées.

Une ressemblance de titre ou de miniature n’est pas une preuve d’auteur original ni de duplication. Les publications gardent leurs identifiants de source ; aucun rapprochement automatique non vérifié n’est appliqué.

Les aperçus sont des liens vers les images publiées par les sources, sans copie locale. Les aperçus MoeWalls sont désactivés conformément aux restrictions relevées. Une attribution n’accorde pas une licence de redistribution. Les conditions et propriétaires indiqués par les sources restent applicables. LivelyWallpaper.app est un catalogue indépendant et n’est pas le projet officiel Lively.

## Connexion avec MPVpaper Engine

Le navigateur ne détecte pas automatiquement une application installée ou ouverte. La version Engine avec l’adaptateur propose **Découvrir → Hub avec mes goûts**, ou :

```bash
python3 ~/.config/mpvpaper-engine/mpvpaper-enginectl.py hub
# Repli si la connexion ou la redirection de connexion ChatGPT perd le fragment :
python3 ~/.config/mpvpaper-engine/mpvpaper-enginectl.py hub --json > mpvp-profile.json
```

Importer ce JSON dans **Connecter Engine** sur le Hub. Le transfert automatique utilise `#mpvp_profile=` avec du JSON encodé par `encodeURIComponent` (Python `quote`). Le fragment ne part pas dans les requêtes HTTP et est retiré de l’adresse dès consommation. Le profil reste seulement dans l’état de cet onglet, sans serveur, cookie, stockage navigateur ni bibliothèque brute. Il est effacé au rechargement ou à la déconnexion du profil.

Le contrat version 1 contient uniquement `version: 1`, `source: "mpvpaper-engine"`, et `preferences: [{tag, weight}]`. Les 16 thèmes autorisés sont définis dans `lib/recommendations.ts`. Chaque poids est compris entre 0,01 et 1. La lecture est limitée à 4 Ko ; les champs supplémentaires, doublons et versions incompatibles sont refusés. Les titres et tags locaux sont analysés sur l’ordinateur avec un vocabulaire fixe ; aucun nom de fichier, chemin, identifiant personnel, date ou historique détaillé n’est transmis.

Engine résume au plus 1 000 fonds non manquants de sa base SQLite, sans scanner les médias ni lancer le service. Poids local : une unité par fond, bonus de quatre pour un favori, bonus d’usage logarithmique plafonné à cinq. Les sommes sont normalisées par le maximum. Une bibliothèque absente ou sans thème reconnu produit un profil vide. La classification est un rapprochement de mots-clés, pas une analyse visuelle des fichiers.

Dans **Mes goûts + découverte**, les filtres sont appliqués avant le mélange. Les `floor(N/2)` meilleures correspondances occupent la moitié des places et alternent avec les fonds restants dans l’ordre de la sélection Hub, sans doublon. Un nombre impair ajoute une découverte. S’il manque des correspondances, elles sont remplacées par des découvertes et le ratio réel est affiché. Le catalogue reste limité aux fonds référencés. Les tris communautaires et la liste des favoris restent inchangés ; le score public n’intègre pas le profil local.

## Organisation du code

| Fichier | Rôle |
| --- | --- |
| `app/page.tsx` | Catalogue, recherche, fiches, favoris et notes |
| `app/globals.css` | Thème sombre et affichage mobile |
| `data/catalog.json` | Métadonnées vérifiées ; aucun fichier vidéo |
| `data/source-review.json` | Vérifications des conditions des sources |
| `lib/recommendations.ts`, `components/engine-connection.tsx` | Contrat Engine, transfert local et mélange des propositions |
| `lib/hub.ts` | Identité, accès D1, événements et classement |
| `app/api/catalog/route.ts` | Catalogue et statistiques communes |
| `app/api/interactions/route.ts` | Vues, favoris et notes |
| `app/api/download/route.ts` | Redirection vers un fichier public répertorié |
| `app/api/manifest/route.ts` | Export de la fiche de provenance |
| `db/schema.ts`, `drizzle/` | Schéma et migrations D1 |
| `scripts/check-hub.mjs` | Vérifications des routes avec SQLite réel |

## Vérification

```bash
node node_modules/typescript/bin/tsc --noEmit
node scripts/check-hub.mjs
node scripts/check-recommendations.mjs
node scripts/run-framework.mjs build
```

Le contrôle vérifie les migrations SQLite, la sauvegarde et l’isolation des favoris, le remplacement d’une note, le refus des notes hors limites, l’authentification des écritures, la protection contre les requêtes d’autres origines, les corps invalides, les IDs inconnus, les quatre redirections, la liste des domaines autorisés, la déduplication quotidienne et la provenance des exports.

Les écritures utilisent des requêtes préparées. Les destinations de téléchargement sont choisies dans le catalogue, jamais à partir d’une URL fournie par le visiteur. Les cookies visiteurs sont HttpOnly, Secure et SameSite=Lax. Les en-têtes d’identité doivent être injectés exclusivement par la plateforme d’hébergement ; ne pas exposer ce serveur directement sur Internet avec des en-têtes d’identité librement fournis par le client.

## Développement et hébergement

Application React/Vinext compatible Cloudflare Workers, avec D1 pour les données communautaires. La plateforme Sites gère les ressources et applique les migrations générées lors de la publication. Ne pas modifier les migrations déjà appliquées en production.

Pour héberger ailleurs, conserver les API et le schéma, remplacer l’accès `cloudflare:workers` par celui de l’hébergeur choisi et ajouter une vraie authentification côté serveur. Aucune clé d’API externe n’est nécessaire à la version actuelle.
