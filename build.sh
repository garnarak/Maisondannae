#!/usr/bin/env bash
# Script de construction utilisé par l'hébergeur à chaque déploiement.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py ensure_admin
