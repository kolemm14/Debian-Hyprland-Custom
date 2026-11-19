# Ouvrir MPVpaper Hub dans VS Code

1. Extraire `mpvpaper-hub-source-v2.zip`.
2. Dans VS Code : Fichier → Ouvrir le dossier → choisir `mpvpaper-hub`.
3. Installer Node.js 22.13 ou une version plus récente si nécessaire.
4. Ouvrir Terminal → Nouveau terminal dans VS Code.
5. Installer le gestionnaire et les dépendances :

```bash
npm install --global pnpm@11.25.0
pnpm install
```

6. Lancer le site :

```bash
pnpm dev
```

Ouvrir l’adresse affichée dans le terminal, normalement http://localhost:5173.

## Activer les statistiques dans la base locale

Si le catalogue affiche des statistiques indisponibles, arrêter le serveur avec Ctrl+C, puis exécuter :

```bash
pnpm build
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_grey_trauma.sql
pnpm dev
```

La base locale est séparée de celle du site publié. L’identité de développement simulée ne doit jamais être utilisée comme authentification sur un serveur public. Le mode de développement portable du projet active cette simulation pour les essais locaux.

## Les fichiers à modifier d’abord

- `app/page.tsx` : interface et interactions.
- `app/globals.css` : couleurs, tailles et affichage mobile.
- `data/catalog.json` : fiches des fonds.
- `app/api/` et `lib/hub.ts` : téléchargement et statistiques.

Le dossier `node_modules`, les caches et les données des utilisateurs du site publié ne sont pas inclus. Aucun jeton de connexion n’est inclus. L’installation des dépendances demande une connexion Internet.

Les modifications locales ne sont pas publiées automatiquement. Voir `README.md` pour le fonctionnement complet du projet.

## Connexion des recommandations à Engine

Lire `CONNEXION_ENGINE.md` pour vérifier la connexion client déjà intégrée dans ce dépôt et lancer le Hub avec les goûts locaux. `lib/recommendations.ts` contient la règle de mélange et `components/engine-connection.tsx` le transfert du profil.
