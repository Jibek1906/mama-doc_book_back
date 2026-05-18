#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py ensure_admin
python manage.py collectstatic --noinput

gunicorn config.wsgi --workers 3 --bind 0.0.0.0:8000 --timeout 120 --log-level info
