# Historique des versions

Les numéros suivent le principe `MAJEUR.MINEUR.CORRECTIF` :
- **correctif** (0.1.0 → 0.1.1) : corrections, pas de nouvelle fonction ;
- **mineur** (0.1 → 0.2) : nouvelles fonctions ;
- **majeur** (0.x → 1.0) : première version définitive, puis changements importants.

Le suffixe `-beta` indique une version de test.

## 0.2.0-beta — 19/10/2026

- Solde au moment de la vente : le vendeur choisit −10, −20, −30, −40, −50 ou −70 %
  du prix de vente initial ; la liste affiche directement le prix soldé
- Chaque vente garde le prix initial, le pourcentage et le prix encaissé ;
  la marge est calculée sur le prix encaissé
- Historique des ventes : prix initial barré et pourcentage affichés
- Synthèse de marge : montant total des soldes accordés dans le mois
- Nouveau design aux couleurs de la boutique : fuchsia, or et ivoire, titres en
  Cormorant Garamond, texte en Jost, logo dans l'en-tête et page de connexion illustrée
- Tablette paysage : la liste du stock s'affiche en cartes sur deux colonnes
- Page Ventes : chiffre d'affaires, pièces vendues et nombre de ventes de la journée
  (et marge du jour pour l'administrateur)
- Page Ventes : totaux du mois en cours et historique des ventes du mois, regroupé
  par jour avec le total de chaque journée, visibles aussi par les vendeurs
- Bouton « Mes ventes » dans la page Ventes : les mêmes chiffres et historiques, limités
  aux ventes enregistrées avec son propre compte ; par défaut, la page montre toute la boutique

## 0.1.1-beta — 17/10/2026

Préparation de la mise en ligne, sans changement fonctionnel.

- Configuration d'hébergement Render (`render.yaml`, `build.sh`, `predeploy.sh`)
- Création automatique du compte administrateur au premier déploiement
- Mise en ligne sur https://maisondannae.onrender.com
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
