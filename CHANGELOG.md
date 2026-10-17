# Historique des versions

Les numéros suivent le principe `MAJEUR.MINEUR.CORRECTIF` :
- **correctif** (0.1.0 → 0.1.1) : corrections, pas de nouvelle fonction ;
- **mineur** (0.1 → 0.2) : nouvelles fonctions ;
- **majeur** (0.x → 1.0) : première version définitive, puis changements importants.

Le suffixe `-beta` indique une version de test.

## 0.1.1-beta — non publiée

Préparation de la mise en ligne, sans changement fonctionnel.

- Configuration d'hébergement Render (`render.yaml`, `build.sh`)
- Création automatique du compte administrateur au premier déploiement
- Pages « Accès refusé » et « Page introuvable » en français
- Numéro de version et mention « Bêta » en bas de page
- Tests lancés automatiquement sur GitHub à chaque modification

## 0.1.0-beta — 17/10/2026

Version de départ.

- Liste du stock avec recherche, vente en un clic depuis la tablette
- Ajustements de stock tracés (réassort, inventaire, casse, retour)
- Rôles administrateur / restreint : coût d'achat, prix et marge réservés à l'administrateur
- Synthèse mensuelle de marge et classement des articles les plus rentables
- Annulation d'une vente (admin), avec remise en stock
- Interface adaptée ordinateur, tablette et téléphone
