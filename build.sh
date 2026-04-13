#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements/base.txt

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createcachetable
