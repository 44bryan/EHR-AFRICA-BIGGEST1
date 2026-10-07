#!/usr/bin/env bash
# =============================================================================
#  EHR Africa — Production Deployment Script
#
#  Run once on a fresh Ubuntu 22.04 / 24.04 server, or re-run for updates.
#
#  Usage:
#    chmod +x deploy.sh
#    sudo ./deploy.sh          # first-time full install
#    sudo ./deploy.sh --update # code update only (skip OS packages)
#
#  What it does (full install):
#    1. Installs OS packages (Python 3, PostgreSQL, Redis, Nginx, Node)
#    2. Creates a dedicated 'ehr' system user
#    3. Sets up PostgreSQL database and user
#    4. Creates Python virtualenv and installs dependencies
#    5. Runs migrations + collectstatic + setup_ehr
#    6. Installs systemd services for Gunicorn + Celery worker + Celery beat
#    7. Configures Nginx as reverse proxy
#    8. Obtains Let's Encrypt SSL certificate (optional)
# =============================================================================

set -euo pipefail

# ── Config — edit these before running ───────────────────────────────────────
APP_USER="ehr"
APP_DIR="/opt/ehr-africa"
VENV_DIR="$APP_DIR/venv"
DOMAIN=""                  # e.g. ehr.myhospital.cm  (leave blank to skip SSL)
DB_NAME="ehr_africa"
DB_USER="ehr_user"
DB_PASS=""                 # will be prompted if blank
PYTHON="python3.11"

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${GREEN}══ $* ══${NC}"; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo ./deploy.sh"

UPDATE_ONLY=false
[[ "${1:-}" == "--update" ]] && UPDATE_ONLY=true

# =============================================================================
#  STEP 1 — OS packages
# =============================================================================
if [[ "$UPDATE_ONLY" == false ]]; then
  section "Installing OS packages"
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    build-essential git curl wget \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    libpq-dev \
    gettext \
    supervisor
  info "OS packages installed"
fi

# =============================================================================
#  STEP 2 — App user
# =============================================================================
if [[ "$UPDATE_ONLY" == false ]]; then
  section "Creating system user: $APP_USER"
  id "$APP_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /bin/bash "$APP_USER"
  mkdir -p "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  info "User '$APP_USER' ready"
fi

# =============================================================================
#  STEP 3 — PostgreSQL
# =============================================================================
if [[ "$UPDATE_ONLY" == false ]]; then
  section "Setting up PostgreSQL"
  systemctl start postgresql
  systemctl enable postgresql

  if [[ -z "$DB_PASS" ]]; then
    read -s -p "  Enter password for database user '$DB_USER': " DB_PASS; echo
  fi

  sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" \
    | grep -q 1 || sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"

  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" \
    | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

  sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
  info "PostgreSQL ready: $DB_NAME / $DB_USER"
fi

# =============================================================================
#  STEP 4 — Redis
# =============================================================================
if [[ "$UPDATE_ONLY" == false ]]; then
  section "Configuring Redis"
  systemctl start redis-server
  systemctl enable redis-server
  info "Redis running"
fi

# =============================================================================
#  STEP 5 — Code & Python environment
# =============================================================================
section "Deploying application code"
cd "$APP_DIR"

# If .env doesn't exist, copy example and remind operator
if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env" 2>/dev/null || true
  warn ".env not found — copied from .env.example. EDIT IT before continuing."
  warn "  nano $APP_DIR/.env"
  exit 1
fi

# Virtualenv
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtualenv"
  sudo -u "$APP_USER" $PYTHON -m venv "$VENV_DIR"
fi

info "Installing Python dependencies"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
info "Dependencies installed"

# =============================================================================
#  STEP 6 — Django setup
# =============================================================================
section "Running Django management commands"
export DJANGO_SETTINGS_MODULE=ehr_project.settings.production

PY="sudo -u $APP_USER $VENV_DIR/bin/python manage.py"

info "Running migrations"
$PY migrate --noinput

info "Collecting static files"
$PY collectstatic --noinput --clear -v 0

info "Creating cache table (fallback)"
$PY createcachetable 2>/dev/null || true

if [[ "$UPDATE_ONLY" == false ]]; then
  info "Running first-time EHR setup"
  $PY setup_ehr
fi

# =============================================================================
#  STEP 7 — Systemd: Gunicorn
# =============================================================================
if [[ "$UPDATE_ONLY" == false ]]; then
  section "Installing Gunicorn systemd service"
  cat > /etc/systemd/system/ehr-gunicorn.service <<EOF
[Unit]
Description=EHR Africa — Gunicorn Application Server
After=network.target postgresql.service redis.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DJANGO_SETTINGS_MODULE=ehr_project.settings.production"
ExecStart=$VENV_DIR/bin/gunicorn \\
    --workers 4 \\
    --worker-class gevent \\
    --bind unix:$APP_DIR/ehr.sock \\
    --timeout 120 \\
    --access-logfile $APP_DIR/logs/gunicorn-access.log \\
    --error-logfile  $APP_DIR/logs/gunicorn-error.log \\
    ehr_project.wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  # =============================================================================
  #  STEP 7b — Systemd: Celery worker
  # =============================================================================
  cat > /etc/systemd/system/ehr-celery.service <<EOF
[Unit]
Description=EHR Africa — Celery Task Worker
After=network.target redis.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DJANGO_SETTINGS_MODULE=ehr_project.settings.production"
ExecStart=$VENV_DIR/bin/celery -A ehr_project worker \\
    --loglevel=info \\
    --logfile=$APP_DIR/logs/celery-worker.log \\
    --concurrency=4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  # =============================================================================
  #  STEP 7c — Systemd: Celery beat (scheduled tasks)
  # =============================================================================
  cat > /etc/systemd/system/ehr-celerybeat.service <<EOF
[Unit]
Description=EHR Africa — Celery Beat Scheduler
After=network.target redis.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment="DJANGO_SETTINGS_MODULE=ehr_project.settings.production"
ExecStart=$VENV_DIR/bin/celery -A ehr_project beat \\
    --loglevel=info \\
    --logfile=$APP_DIR/logs/celery-beat.log \\
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable  ehr-gunicorn ehr-celery ehr-celerybeat
  systemctl restart ehr-gunicorn ehr-celery ehr-celerybeat
  info "Gunicorn + Celery services enabled and started"

  # =============================================================================
  #  STEP 8 — Nginx
  # =============================================================================
  section "Configuring Nginx"
  NGINX_CONF="/etc/nginx/sites-available/ehr-africa"
  cat > "$NGINX_CONF" <<EOF
upstream ehr_app {
    server unix:$APP_DIR/ehr.sock fail_timeout=0;
}

server {
    listen 80;
    server_name ${DOMAIN:-_};

    client_max_body_size 20M;

    # Static files served directly by Nginx (much faster than Gunicorn)
    location /static/ {
        alias $APP_DIR/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias $APP_DIR/media/;
        expires 30d;
    }

    location / {
        proxy_pass         http://ehr_app;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
        proxy_connect_timeout 10;
    }

    # Security headers
    add_header X-Frame-Options          DENY;
    add_header X-Content-Type-Options   nosniff;
    add_header Referrer-Policy          strict-origin-when-cross-origin;
}
EOF

  ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/ehr-africa
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl restart nginx
  info "Nginx configured"

  # =============================================================================
  #  STEP 9 — SSL (optional)
  # =============================================================================
  if [[ -n "$DOMAIN" ]]; then
    section "Obtaining SSL certificate for $DOMAIN"
    apt-get install -y certbot python3-certbot-nginx -q
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
      --email "$(grep HOSPITAL_EMAIL $APP_DIR/.env | cut -d= -f2)" \
      --redirect || warn "Certbot failed — run manually: certbot --nginx -d $DOMAIN"
    # Auto-renew
    systemctl enable certbot.timer 2>/dev/null || true
    info "SSL certificate obtained"
  fi
fi   # end UPDATE_ONLY == false block

# =============================================================================
#  Update path — reload services after code pull
# =============================================================================
if [[ "$UPDATE_ONLY" == true ]]; then
  section "Reloading services after update"
  export DJANGO_SETTINGS_MODULE=ehr_project.settings.production
  PY="sudo -u $APP_USER $VENV_DIR/bin/python manage.py"
  $PY migrate --noinput
  $PY collectstatic --noinput --clear -v 0
  systemctl reload  ehr-gunicorn  2>/dev/null || systemctl restart ehr-gunicorn
  systemctl restart ehr-celery ehr-celerybeat
  info "Update complete — services reloaded"
fi

# =============================================================================
#  Done
# =============================================================================
section "Deployment complete"
echo ""
echo "  Application: http://${DOMAIN:-<server-ip>}"
echo "  Logs dir:    $APP_DIR/logs/"
echo ""
echo "  Useful commands:"
echo "    journalctl -u ehr-gunicorn -f          # Gunicorn live log"
echo "    journalctl -u ehr-celery   -f          # Celery live log"
echo "    sudo systemctl status ehr-gunicorn      # Service status"
echo "    python manage.py backup_db              # Manual DB backup"
echo ""
