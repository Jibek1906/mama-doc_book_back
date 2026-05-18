#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py ensure_admin

# Собираем статику в STATIC_ROOT, чтобы картинки (иконки/фото)
# гарантированно были доступны по /static/ даже в DEV.
python manage.py collectstatic --noinput

# В режиме DEBUG runserver по умолчанию включает StaticFilesHandler,
# который ищет статику через finders (STATICFILES_DIRS / app static dirs),
# и не отдаёт файлы из STATIC_ROOT.
# Мы складываем картинки в /app/static (STATIC_ROOT), поэтому отключаем
# встроенный обработчик статики, чтобы работали URL-паттерны из config/urls.py.
python manage.py runserver --nostatic 0.0.0.0:8000
