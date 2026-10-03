#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear
python manage.py bootstrap_admin

if [ "${BOOTSTRAP_DEMO:-false}" = "true" ]; then
  python manage.py bootstrap_demo
fi

exec "$@"
