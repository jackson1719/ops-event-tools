#!/usr/bin/env bash
# Install/update ops-event-tools: system packages, venv, migrations,
# static files, and systemd units. Idempotent — safe to re-run for upgrades.
#
# Usage: ./deploy/install.sh          (run as the app user; sudo used where needed)
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> Installing system packages (poppler-utils for PDF conversion)"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv poppler-utils

echo "==> Setting up virtualenv"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
    echo "==> Creating .env from template (EDIT IT: set SECRET_KEY and ALLOWED_HOSTS)"
    cp .env.example .env
    SECRET=$(./venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
fi

if [ ! -f credentials.json ] && ! grep -q "^GOOGLE_CREDENTIALS_FILE=/" .env; then
    echo "WARNING: no credentials.json found — Google Sheets sync will fail until"
    echo "         you add a service-account key (or set GOOGLE_CREDENTIALS_FILE in .env)."
fi

echo "==> Running migrations"
./venv/bin/python manage.py migrate --noinput

echo "==> Collecting static files"
./venv/bin/python manage.py collectstatic --noinput | tail -1

echo "==> Installing systemd units"
sudo cp deploy/ops-event-tools.service deploy/ops-sync.service deploy/ops-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ops-event-tools ops-sync.timer

echo "==> (Re)starting services"
sudo systemctl restart ops-event-tools
sudo systemctl start ops-sync.timer

echo
echo "Done. Service status:"
systemctl --no-pager --lines=0 status ops-event-tools ops-sync.timer | grep -E 'ops-|Active:'
echo
echo "Next steps if this is a fresh install:"
echo "  ./venv/bin/python manage.py createsuperuser"
echo "  Create an Event in /admin/, then: ./venv/bin/python manage.py sync_events <slug>"
