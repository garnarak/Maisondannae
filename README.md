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

## Installer l'application sur un téléphone ou une tablette

L'outil s'installe comme une application, avec l'icône Maison d'Annaé sur l'écran
d'accueil et une ouverture en plein écran :

- **iPhone / iPad** : ouvrir le site dans **Safari**, toucher **Partager**, puis
  **Sur l'écran d'accueil**.
- **Android** : ouvrir le site dans **Chrome**, menu **⋮**, puis **Installer l'application**
  (ou **Ajouter à l'écran d'accueil**).

Les mises à jour publiées sur le serveur sont disponibles immédiatement, sans rien
réinstaller. Une connexion internet reste nécessaire.

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
