# Historique des versions

Les numéros suivent le principe `MAJEUR.MINEUR.CORRECTIF` :
- **correctif** (0.1.0 → 0.1.1) : corrections, pas de nouvelle fonction ;
- **mineur** (0.1 → 0.2) : nouvelles fonctions ;
- **majeur** (0.x → 1.0) : première version définitive, puis changements importants.

Le suffixe `-beta` indique une version de test.

## 2.2.0 — 22/11/2026

- Onglet « Rupture » supprimé (les articles ne sont pas rachetés à l'identique) : l'onglet
  Stock montre les articles disponibles, et la case « Voir aussi les articles épuisés »
  affiche aussi ceux à 0 pièce (pour corriger une vente ou faire un réassort exceptionnel)
- Shopify : un modèle épuisé (plus aucune pièce dans ses tailles et couleurs) est
  automatiquement archivé, donc retiré de la boutique en ligne ; s'il revient en stock, il
  retrouve son statut d'avant (actif ou brouillon). Un produit archivé à la main n'est jamais
  remis en ligne par l'outil
- Shopify, « Créer les produits manquants » : les modèles épuisés ne sont plus créés
- Shopify, « Tout renvoyer à Shopify » : se fait en arrière-plan (suivi dans le journal) et
  archive au passage les produits déjà épuisés

## 2.1.0 — 17/11/2026

- Couleurs d'une variante (« Nouveau modèle » et Stock → Modifier) : une couleur cochée donne
  une variante unie, **deux couleurs cochées donnent une variante bicolore** (ex. « Blanc /
  Terracotta »), dans l'ordre où elles sont cochées ; la variante qui sera créée s'affiche
  sous les couleurs. Les autres couleurs d'un même modèle s'ajoutent ensuite, une par une,
  sur la page du modèle
- Stock → Modifier, « Ajouter des tailles ou des couleurs » : la taille est obligatoire ; sans
  taille sélectionnée, un message demande de la choisir et rien n'est ajouté
- Seules les couleurs simples sont proposées en pastilles ; les couleurs doubles apparaissent
  telles quelles sur les variantes, dans Shopify et dans Excel
- SKU d'une couleur double lisible (`…-M-BLA-TER`) ; deux couleurs aux noms proches ne
  bloquent plus la création des variantes (le SKU est numéroté)
- Téléphone, page du modèle (Stock → Modifier) : affichage sur une seule colonne
- Onglets du navigateur des pages Stock et Caisse : le titre n'affiche plus de code

## 2.0.1 — 16/11/2026

- Shopify, « Créer les produits manquants » :
  - un produit supprimé à la main dans Shopify est recréé (le lien est vérifié à chaque fois) ;
  - un produit déjà dans Shopify auquel il manque des tailles ou couleurs n'est jamais créé
    en double : les variantes manquantes et leur SKU sont listées dans le journal
- Article à taille unique décliné ensuite en tailles ou couleurs : sa variante « Taille unique »
  est masquée dès qu'elle n'a plus de stock (un message l'indique sur la page du modèle) ;
  ses ventes passées restent dans Ventes, Marge et les exports, et elle réapparaît si une
  pièce revient en stock (vente annulée, retour)

## 2.0.0 — 16/11/2026

- Couplage avec la boutique Shopify, par le SKU des variantes :
  - le stock de l'outil est envoyé à Shopify après chaque vente, annulation, ajustement,
    entrée en stock ou import Excel ; les changements de prix aussi ;
  - les commandes Shopify deviennent des ventes « En ligne » (prix payé, réductions déduites)
    et diminuent le stock ; annulations et retours remettent les articles en stock ;
  - une même commande n'est jamais enregistrée deux fois ; les notifications non signées
    par Shopify sont refusées
- Administration → Shopify : état du couplage, test de connexion, création en brouillon des
  produits absents de Shopify, renvoi complet du stock et des prix, journal des échanges
- Administration → Commandes Shopify : liste des commandes reçues
- Couplage inactif tant que les variables `SHOPIFY_*` ne sont pas renseignées sur Render

## 1.5.0 — 16/11/2026

- Modèles et variantes : un modèle (nom, catégorie, coût, prix) se décline en variantes
  de taille (TU, XS, S, M, L, XL, XXL) et de couleur ; chaque variante a son stock et son SKU
- « Nouveau modèle » : les tailles et couleurs cochées créent toutes les variantes d'un coup
- Page du modèle (bouton « Modifier ») : prix et coût communs, entrée en stock de toutes les
  variantes en une fois, ajout de tailles ou de couleurs
- Couleurs choisies dans une liste, modifiable dans Administration → Couleurs
- Stock : variantes regroupées par modèle, de la plus petite à la plus grande taille, avec
  « taille · couleur » sous le nom ; Rupture et Ventes indiquent la variante
- Marge : articles les plus rentables regroupés par modèle
- Excel : une ligne par variante (colonnes MODÈLE, TAILLE, COULEUR, SKU) ; les anciens fichiers
  sans taille s'importent toujours
- Les articles existants deviennent des modèles à taille unique, sans perte de données

## 1.4.3 — 11/11/2026

- Téléphone, onglet Stock (administrateur) : « Coût d'achat total » et « Prix de vente
  total » côte à côte, à parts égales
- Téléphone, onglet Stock : bouton « Nouvelle référence » sur la même ligne que le filtre
  de catégorie, pour que les articles apparaissent plus haut
- Ventes (administrateurs) : bouton « Paiement » pour corriger le mode de paiement d'une
  vente en boutique, sans changer sa date, sa vendeuse, son article ni son prix ; la caisse
  et le suivi espèces / CB se mettent à jour, et chaque correction est tracée dans
  Administration → Corrections de paiement
- Téléphone, Ventes : le mode de paiement s'affiche sous le total, aligné à droite

## 1.4.2 — 02/11/2026

- Stock : le nombre d'articles et de références s'affiche à côté du titre « Stock »,
  à la place de la grande case « Articles en stock » (gain de place, surtout sur téléphone)
- Nouvelle référence et Modifier : le champ « Catégorie » vient avant « Désignation »
- Marge : l'indicateur « Taux de marge » est renommé « Taux de marque » (marge ÷ prix de
  vente) et un vrai « Taux de marge » (marge ÷ coût d'achat) est ajouté, dans les cases
  et dans les tableaux par canal, par article et par mois

## 1.4.1 — 02/11/2026

- Stock, Rupture et Ventes : colonne « Catégorie » en premier, puis « Désignation »
  (dans Ventes, la colonne « Référence » devient « Désignation »)

## 1.4.0 — 02/11/2026

- Nouvel onglet « Rupture » : tableau des articles à 0 pièce (désignation, catégorie,
  prix, dernière vente) avec accès à « Ajuster » pour le réassort
- Les articles en rupture n'apparaissent plus dans l'onglet « Stock » ; ils y reviennent
  dès que leur quantité repasse au-dessus de 0
- Nombre d'articles en rupture affiché à côté de « Rupture » dans le menu

## 1.3.0 — 31/10/2026

- Administration → « Import / export Excel » :
  - export du stock (réimportable tel quel) et des ventes sur une période choisie ;
  - import du stock depuis Excel, avec écran de vérification avant confirmation
    (créations, mises à jour, erreurs, points à vérifier)
- À l'import : référence existante mise à jour, catégorie inconnue créée automatiquement,
  changements de quantité tracés en ajustements « Import Excel »

## 1.2.0 — 31/10/2026

- Liste du stock : nombre d'articles en stock (et de références) pour tous les comptes
- Administrateurs : coût d'achat total et prix de vente total du stock
- Les totaux suivent la recherche et le filtre par catégorie

## 1.1.0 — 31/10/2026

- Catégories d'articles : Veste, Pantalon, Jean, Chemise, Pull, Débardeur,
  T-shirt manche longue ; d'autres se créent dans Administration → Catégories
- Catégorie obligatoire à la création d'une référence, modifiable avec « Modifier »
- Liste du stock : catégorie affichée sous le nom de chaque article, et filtre par
  catégorie à côté de la recherche
- Bouton « En ligne » : confirmation demandée avant d'enregistrer la vente

## 1.0.0 — 29/10/2026

Première version de production.

- Fin de la phase de test : la mention « Bêta » disparaît du bas de page
- Alertes par e-mail : chaque erreur du site est envoyée aux administrateurs
  (adresses et serveur d'envoi à renseigner sur Render)
- Les erreurs restent aussi visibles dans les journaux Render
- Page d'erreur en français, qui invite à vérifier la dernière vente avant de la refaire

## 0.5.1-beta — 29/10/2026

- Commande `vider_donnees_de_test` pour supprimer les données de test (références,
  ventes, ajustements, récupérations d'espèces) avant de saisir le vrai stock ;
  les comptes utilisateurs sont conservés

## 0.5.0-beta — 28/10/2026

- Application installable sur téléphone et tablette (iPhone, iPad, Android) :
  icône Maison d'Annaé sur l'écran d'accueil et ouverture en plein écran,
  sans barre d'adresse
- Page « Pas de connexion » quand le réseau est coupé
- Nouvelles icônes tirées du logo (écran d'accueil, onglet du navigateur)

## 0.4.0-beta — 27/10/2026

- Paiement des ventes en boutique : après « Vendre », choix entre espèces,
  carte bancaire ou espèces + CB (le vendeur indique alors le montant en espèces)
- Mode de paiement affiché sous le total de chaque vente
- Nouvelle page Caisse (administrateurs) : espèces théoriquement en caisse,
  récupération des espèces en laissant un fond de 30 € modifiable,
  historique des récupérations et suivi mensuel espèces / CB / espèces récupérées
- Les comptes restreints ne peuvent pas récupérer les espèces

## 0.3.0-beta — 21/10/2026

- Ventes en ligne : bouton « En ligne » à côté de « Vendre » sur la liste du stock,
  accessible à tous ; « Vendre » enregistre une vente en boutique
- Étiquette « En ligne » sur les ventes concernées dans les listes
- Les ventes en ligne ne sont attribuées à aucun vendeur : elles ne comptent ni dans
  « Mes ventes » ni dans les chiffres d'une vendeuse ; la personne qui les a saisies
  reste visible dans l'administration
- Page Ventes : bouton « Ventes en ligne » pour suivre les chiffres de ce canal
- Page Ventes : chiffre d'affaires du jour et du mois réparti entre boutique et en ligne
- Synthèse de marge : chiffre d'affaires et marge du mois par canal

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
- Administrateur : un bouton par vendeuse dans la page Ventes, pour voir ses chiffres
  et son historique du jour et du mois

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
