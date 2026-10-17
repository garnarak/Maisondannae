#!/usr/bin/env bash
# Avant chaque mise en service : mise à jour de la base et création du compte administrateur.
set -o errexit

python manage.py migrate --noinput
python manage.py ensure_admin
