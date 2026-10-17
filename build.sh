#!/usr/bin/env bash
# Construction : installation et fichiers statiques. La base n'est pas accessible à cette étape.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
