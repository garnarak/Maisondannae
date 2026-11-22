# Maison d'Annae — gestion de stock

Application web (Django) pour gérer le stock de la boutique : références, ventes,
ajustements de stock et synthèse mensuelle de la marge. Utilisable sur ordinateur et tablette.

## Rôles

| | Administrateur | Restreint |
| --- | --- | --- |
| Voir le prix de vente et le stock | oui | oui |
| Enregistrer une vente, ajuster le stock | oui | oui |
| Voir le coût d'achat et la marge | oui | non |
| Créer une référence, modifier les prix | oui | non |
| Annuler une vente, gérer les comptes (`/admin/`) | oui | non |
| Historique des ventes | complet | ventes du jour |

## Règles de gestion

- **Vente** : bouton « Vendre » sur la liste du stock. La vente décrémente le stock et
  fige le prix de vente et le coût d'achat du moment, pour que la marge passée ne change
  pas si les prix évoluent.
- **Solde** : au moment de la vente, le vendeur peut appliquer −10, −20, −30, −40, −50
  ou −70 % au prix de vente (arrondi au centime). La marge est calculée sur le prix encaissé.
- **Ajustement** : réception, casse, inventaire… Tracé avec un motif, mais n'entre pas
  dans la marge. Le stock ne peut jamais devenir négatif.
- **Marge** = (prix de vente − coût d'achat) × quantité, sur les ventes du mois.
- Chaque vente porte un `canal` (magasin / en ligne) pour préparer la boutique en ligne.

## Lancer en local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # compte administrateur
.venv/bin/python manage.py runserver
```

Puis ouvrir http://127.0.0.1:8000. Les autres comptes se créent dans
**Administration → Utilisateurs** (rôle « Restreint » par défaut).

Tests : `.venv/bin/python manage.py test`

## Import / export Excel

Dans **Administration → Import / export Excel** (administrateurs uniquement) :

- **Exporter le stock** : un fichier au même format que l'import, modifiable puis réimportable.
- **Exporter les ventes** d'une période : une ligne par vente (prix, solde, coût, marge, canal,
  paiement, vendeuse).
- **Importer le stock** : une ligne par variante, colonnes `MODÈLE` (ou `DÉSIGNATION`), `CATÉGORIE`,
  `TAILLE`, `COULEUR`, `SKU`, `COÛT D'ACHAT`, `PRIX DE VENTE`, `QUANTITÉ EN STOCK` et, facultativement, `ACTIVE`. Un écran de vérification liste les créations,
  les mises à jour et les erreurs ; rien n'est enregistré avant la confirmation.

## Installer l'application sur un téléphone ou une tablette

L'outil s'installe comme une application, avec l'icône Maison d'Annaé sur l'écran
d'accueil et une ouverture en plein écran :

- **iPhone / iPad** : ouvrir le site dans **Safari**, toucher **Partager**, puis
  **Sur l'écran d'accueil**.
- **Android** : ouvrir le site dans **Chrome**, menu **⋮**, puis **Installer l'application**
  (ou **Ajouter à l'écran d'accueil**).

Les mises à jour publiées sur le serveur sont disponibles immédiatement, sans rien
réinstaller. Une connexion internet reste nécessaire.

## Alertes par e-mail

En production, chaque erreur du site envoie un e-mail détaillé aux administrateurs.
À renseigner dans Render (service **maisondannae** → **Environment**) :

| Variable | Exemple |
| --- | --- |
| `DJANGO_ADMINS` | `garnik@exemple.fr` (plusieurs adresses séparées par des virgules) |
| `DJANGO_EMAIL_HOST` | `smtp.gmail.com` |
| `DJANGO_EMAIL_HOST_USER` | l'adresse Gmail qui envoie |
| `DJANGO_EMAIL_HOST_PASSWORD` | un **mot de passe d'application** Gmail (pas le mot de passe habituel) |
| `DJANGO_EMAIL_PORT` | `587` (valeur par défaut) |

Pour vérifier l'envoi, dans le **Shell** Render : `python manage.py sendtestemail --admins`.

## Shopify

L'outil fait foi pour le stock et les prix ; la boutique Shopify suit automatiquement.

- **Outil → Shopify** : après chaque vente, annulation, ajustement, entrée en stock ou import
  Excel, la quantité de la variante est envoyée à Shopify ; un changement de prix d'un modèle
  est envoyé à toutes ses variantes. Le lien se fait par le **SKU** (identique des deux côtés).
- **Shopify → outil** : chaque commande en ligne devient une vente « En ligne » (prix payé,
  réductions déduites, attribuée à personne) et diminue le stock ; une annulation ou un retour
  remis en stock remet les articles dans l'outil.
- **Produits épuisés** : quand un modèle n'a plus aucune pièce, l'outil l'archive dans Shopify
  (il disparaît de la boutique en ligne) ; s'il revient en stock, il retrouve son statut d'avant.
- Si Shopify est injoignable, la vente est tout de même enregistrée ; l'écart est noté dans
  Administration → Shopify, où le bouton « Tout renvoyer à Shopify » le corrige.

### Mise en place (une seule fois)

1. Dans Shopify : **Paramètres → Applications → Développer des applications** (Dev Dashboard),
   créer une application « Maison d'Annae — stock » avec les autorisations
   `read_products`, `write_products`, `read_inventory`, `write_inventory`, `read_locations`,
   `read_orders`, puis l'installer sur la boutique.
2. Copier son **Client ID** et son **Client secret** (ne les envoyer à personne).
3. Dans Render, service **maisondannae** → **Environment**, ajouter :

   | Variable | Valeur |
   | --- | --- |
   | `SHOPIFY_SHOP` | `pvwcah-c9.myshopify.com` |
   | `SHOPIFY_CLIENT_ID` | le Client ID |
   | `SHOPIFY_CLIENT_SECRET` | le Client secret |

   (Avec une ancienne « application personnalisée », mettre son jeton `shpat_…` dans
   `SHOPIFY_ACCESS_TOKEN` et son secret dans `SHOPIFY_WEBHOOK_SECRET`.)
4. Dans l'outil, **Administration → Shopify** :
   - **Tester la connexion** ;
   - **Créer les produits manquants** : chaque modèle est créé dans Shopify **en brouillon**,
     avec ses tailles, couleurs, prix, SKU et quantités (photos et descriptions à ajouter
     dans Shopify, puis publier) ; les produits déjà présents avec le même SKU sont simplement liés ;
   - **Recevoir les commandes** : abonne l'outil aux commandes, annulations et remboursements.

### Ajouter une taille ou une couleur à un article déjà dans Shopify

L'outil ne modifie jamais un produit existant de Shopify (photos et descriptions restent
intactes). Après avoir ajouté la variante dans l'outil :

- produit **pas encore en vente** : le supprimer dans Shopify, puis cliquer sur
  « Créer les produits manquants » ;
- produit **déjà en vente** : ajouter la variante dans Shopify en lui donnant **le même SKU**
  que dans l'outil (visible sur la page du modèle) ; l'outil la reconnaît et lui envoie son stock.

## Gestion des versions

- La branche `main` contient toujours une version stable, prête à être mise en ligne.
- Chaque évolution se fait sur une branche dédiée, puis passe par une *pull request* :
  les tests se lancent automatiquement sur GitHub avant la fusion dans `main`.
- Une version publiée = une *release* GitHub avec son étiquette (`v0.1.0-beta`, …),
  le numéro mis à jour dans `APP_VERSION` (`config/settings.py`) et une entrée dans
  `CHANGELOG.md`.

## Mise en ligne (Render)

Le fichier `render.yaml` décrit l'installation complète : l'application et sa base PostgreSQL.

1. Créer un compte sur [render.com](https://render.com) avec son compte GitHub.
2. **New → Blueprint**, choisir le dépôt `Maisondannae`.
3. Renseigner `DJANGO_ADMIN_USERNAME` et `DJANGO_ADMIN_PASSWORD` : le compte
   administrateur est créé au premier déploiement.
4. Valider. L'adresse publique s'affiche une fois le déploiement terminé
   (de la forme `https://maisondannae.onrender.com`).

Chaque fusion dans `main` redéploie automatiquement l'application.

Variables d'environnement reconnues :

| Variable | Rôle |
| --- | --- |
| `DJANGO_DEBUG` | `0` en production |
| `DJANGO_SECRET_KEY` | clé secrète (générée par Render) |
| `DATABASE_URL` | base PostgreSQL (fournie par Render) |
| `DJANGO_ADMIN_USERNAME`, `DJANGO_ADMIN_PASSWORD` | compte administrateur créé au premier déploiement |
| `DJANGO_ALLOWED_HOSTS` | noms de domaine supplémentaires (ex. un domaine personnalisé) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` + ces mêmes domaines |
