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

## Déploiement

Variables d'environnement à définir en production :

| Variable | Exemple |
| --- | --- |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | une longue chaîne aléatoire |
| `DJANGO_ALLOWED_HOSTS` | `stock.maisondannae.fr` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://stock.maisondannae.fr` |
| `DATABASE_URL` | `postgres://user:pass@host:5432/db` |

Le `Procfile` convient aux hébergeurs de type Railway, Render ou Heroku :
migrations au déploiement, puis `gunicorn`. Lancer aussi
`python manage.py collectstatic --noinput` à la construction.
