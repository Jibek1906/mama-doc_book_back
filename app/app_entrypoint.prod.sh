#!/bin/sh
set -e

# IMPORTANT:
# Project was originally shipped with app_label='clinic'.
# We renamed the app to 'organizations' (including admin URLs /admin/organizations/*).
# On existing DBs we must rename tables + update django_migrations/contenttypes BEFORE running migrate.
python manage.py rename_clinic_app_to_organizations || true

python manage.py migrate --noinput
python manage.py ensure_admin
python manage.py collectstatic --noinput

gunicorn config.wsgi --workers 3 --bind 0.0.0.0:8000 --timeout 120 --log-level info
