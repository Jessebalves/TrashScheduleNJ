#!/usr/bin/env bash
#
# TrashScheduleNJ installer for Ubuntu (tested on 26.04 LTS).
#
#   git clone -b <branch> https://github.com/Jessebalves/TrashScheduleNJ.git
#   cd TrashScheduleNJ
#   sudo ./install.sh
#
# The script is safe to run again: it updates the code, rebuilds the Python
# environment, and leaves existing address data and the database password alone.
#
# What it sets up:
#   - apt packages: python3 + venv, nginx, mysql-server
#   - the code in        $INSTALL_DIR/app
#   - a Python venv in   $INSTALL_DIR/venv
#   - MySQL database `trashschedule`, the `addresses` table (imported from the
#     files in data/ whenever they have changed) and a read-only MySQL user
#     for the web server
#   - the database credentials in /etc/trashschedulenj/trashschedule.env
#   - the python_server systemd service
#   - the nginx site
#
# What it does NOT do: DNS records and the TLS certificate. Put the certificate
# and key at $SSL_CERT and $SSL_KEY and run this script again to switch nginx to
# HTTPS; without them the site is served over plain HTTP on port 80.
#
# MySQL admin access: on a fresh server root logs in through the socket and no
# password is needed. If MySQL root has a password, pass it in or type it when
# asked:
#   sudo MYSQL_ROOT_PASSWORD='...' ./install.sh
#
# Google Maps address search: pass the key once, it is remembered after that.
# Without a key the website shows boxes to type the address in instead.
#   sudo GOOGLE_MAPS_API_KEY='...' ./install.sh
#
# Other settings (all optional, shown with their defaults):
#   INSTALL_DIR=/trashschedulenj
#   SERVER_NAME="trashschedulenj.com www.trashschedulenj.com"
#   SSL_CERT=/etc/ssl/cert.pem  SSL_KEY=/etc/ssl/key.pem
#   REIMPORT=1    build the address table again even if data/ has not changed

set -euo pipefail
umask 022

INSTALL_DIR="${INSTALL_DIR:-/trashschedulenj}"
APP_DIR="$INSTALL_DIR/app"
VENV_DIR="$INSTALL_DIR/venv"
ENV_DIR=/etc/trashschedulenj
ENV_FILE="$ENV_DIR/trashschedule.env"
WEB_ROOT=/var/www/trashschedulenj
SERVER_NAME="${SERVER_NAME:-trashschedulenj.com www.trashschedulenj.com}"
SSL_CERT="${SSL_CERT:-/etc/ssl/cert.pem}"
SSL_KEY="${SSL_KEY:-/etc/ssl/key.pem}"
DB_NAME=trashschedule
DB_USER=trashschedule
SERVICE=python_server
NGINX_SITE=/etc/nginx/sites-available/trashschedulenj
REIMPORT="${REIMPORT:-0}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR=""

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
cleanup() { [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR"; return 0; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || fail "Run this script with sudo: sudo ./install.sh"
for f in test_server.py address_lookup.py pickup_schedule.py importcsvtoDatabase.py requirements.txt \
         data/elizabeth.csv towns/elizabeth.json \
         Trash_Schedule_Website/index.html deploy/python_server.service; do
    [ -e "$SRC_DIR/$f" ] || fail "$f is missing from $SRC_DIR. Run install.sh from a full checkout."
done
TMP_DIR="$(mktemp -d)"

# Fill the @PLACEHOLDERS@ in a file from deploy/ and print the result
render() {
    sed -e "s|@APP_DIR@|$APP_DIR|g" \
        -e "s|@VENV_DIR@|$VENV_DIR|g" \
        -e "s|@ENV_FILE@|$ENV_FILE|g" \
        -e "s|@WEB_ROOT@|$WEB_ROOT|g" \
        -e "s|@SERVER_NAME@|$SERVER_NAME|g" \
        -e "s|@SSL_CERT@|$SSL_CERT|g" \
        -e "s|@SSL_KEY@|$SSL_KEY|g" "$1"
}

# ---------------------------------------------------------------- packages
step "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
PACKAGES=(python3 python3-venv nginx mysql-server curl openssl ca-certificates tzdata)
apt-get update -q || echo "WARNING: apt-get update reported a problem, continuing."
if ! apt-get install -y -q "${PACKAGES[@]}"; then
    # apt also fails when an unrelated package on the system is broken (for
    # example a half-configured bootloader package after a release upgrade).
    # Only stop if one of the packages this site needs is really missing.
    for pkg in "${PACKAGES[@]}"; do
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q '^install ok installed$' \
            || fail "Package $pkg could not be installed. Fix the apt errors above and run install.sh again."
    done
    echo
    echo "WARNING: apt reported errors from packages this site does not use."
    echo "Everything TrashScheduleNJ needs is installed, continuing."
fi
python3 -c 'import ensurepip' 2>/dev/null || fail "python3-venv is not usable (ensurepip missing)."
systemctl enable --now mysql nginx

# -------------------------------------------------------------------- code
step "Copying the code to $APP_DIR"
mkdir -p "$INSTALL_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    rm -rf "$APP_DIR.new"
    mkdir -p "$APP_DIR.new"
    cp -r "$SRC_DIR/Trash_Schedule_Website" \
          "$SRC_DIR/test_server.py" \
          "$SRC_DIR/address_lookup.py" \
          "$SRC_DIR/pickup_schedule.py" \
          "$SRC_DIR/importcsvtoDatabase.py" \
          "$SRC_DIR/towns" \
          "$SRC_DIR/requirements.txt" "$APP_DIR.new/"
    #Only the address files themselves, not the reference material under data/
    mkdir "$APP_DIR.new/data"
    cp "$SRC_DIR"/data/*.csv "$APP_DIR.new/data/"
    rm -rf "$APP_DIR"
    mv "$APP_DIR.new" "$APP_DIR"
fi
chown -R root:root "$APP_DIR"
chmod -R u=rwX,go=rX "$APP_DIR"

# -------------------------------------------------------------------- venv
step "Building the Python environment in $VENV_DIR ($(python3 --version))"
python3 -m venv --clear "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---------------------------------------------------------------- database
step "Setting up the MySQL database"
MYSQL=(mysql --protocol=socket -uroot)
if ! "${MYSQL[@]}" -e 'SELECT 1' >/dev/null 2>&1; then
    if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then
        [ -t 0 ] || fail "MySQL root needs a password. Run: sudo MYSQL_ROOT_PASSWORD='...' ./install.sh"
        read -r -s -p "MySQL root password: " MYSQL_ROOT_PASSWORD
        echo
    fi
    escaped="${MYSQL_ROOT_PASSWORD//\\/\\\\}"
    escaped="${escaped//\"/\\\"}"
    (umask 077; printf '[client]\nuser=root\npassword="%s"\n' "$escaped" > "$TMP_DIR/admin.cnf")
    MYSQL=(mysql --defaults-extra-file="$TMP_DIR/admin.cnf")
    "${MYSQL[@]}" -e 'SELECT 1' >/dev/null 2>&1 || fail "Could not log in to MySQL as root with that password."
fi

# Keep the web server's database password across runs; make one the first time
DB_PASSWORD=""
MAPS_KEY="${GOOGLE_MAPS_API_KEY:-}"
if [ -f "$ENV_FILE" ]; then
    DB_PASSWORD="$(sed -n 's/^DB_PASSWORD=//p' "$ENV_FILE" | head -n 1)"
    # The Google Maps key is kept too, unless a new one was passed in
    [ -n "$MAPS_KEY" ] || MAPS_KEY="$(sed -n 's/^GOOGLE_MAPS_API_KEY=//p' "$ENV_FILE" | head -n 1)"
fi
[ -n "$DB_PASSWORD" ] || DB_PASSWORD="$(openssl rand -hex 24)"

"${MYSQL[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
SQL

# The address table is built from the files in data/. It is built again when
# those files have changed since the last import (or the table is missing, or
# still has the columns from before more towns were added).
mkdir -p "$ENV_DIR"
DATA_SUM_FILE="$ENV_DIR/addresses.sha256"
data_sum="$(cat "$APP_DIR"/data/*.csv | sha256sum | cut -d' ' -f1)"
has_zone="$("${MYSQL[@]}" -N -B -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='$DB_NAME' AND table_name='addresses' AND column_name='Zone'")"
row_count=0
[ "$has_zone" = "1" ] && row_count="$("${MYSQL[@]}" -N -B -e "SELECT COUNT(*) FROM \`$DB_NAME\`.addresses")"
if [ "$row_count" = "0" ] || [ "$REIMPORT" = "1" ] || [ "$(cat "$DATA_SUM_FILE" 2>/dev/null)" != "$data_sum" ]; then
    echo "Importing addresses from the data folder"
    python3 "$APP_DIR/importcsvtoDatabase.py" > "$TMP_DIR/addresses.sql"
    "${MYSQL[@]}" "$DB_NAME" < "$TMP_DIR/addresses.sql"
    row_count="$("${MYSQL[@]}" -N -B -e "SELECT COUNT(*) FROM \`$DB_NAME\`.addresses")"
    echo "$data_sum" > "$DATA_SUM_FILE"
else
    echo "The address files have not changed, keeping the addresses table (set REIMPORT=1 to build it again)"
fi
echo "Rows in addresses: $row_count"
"${MYSQL[@]}" -N -B -e "SELECT CONCAT('  ', Municipality, ': ', COUNT(*)) FROM \`$DB_NAME\`.addresses GROUP BY Municipality ORDER BY Municipality"

mkdir -p "$ENV_DIR"
(umask 077; cat > "$ENV_FILE" <<ENV
# Written by install.sh. Read by the $SERVICE systemd service.
DB_HOST=localhost
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
PORT=5000
GOOGLE_MAPS_API_KEY=$MAPS_KEY
ENV
)
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ----------------------------------------------------------------- service
step "Installing the $SERVICE service"
render "$SRC_DIR/deploy/python_server.service" > "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"

# ------------------------------------------------------------------- nginx
step "Configuring nginx"
if [ -e "$WEB_ROOT" ] && [ ! -L "$WEB_ROOT" ]; then
    mv "$WEB_ROOT" "$WEB_ROOT.bak.$(date +%Y%m%d%H%M%S)"
fi
mkdir -p "$(dirname "$WEB_ROOT")"
ln -sfn "$APP_DIR/Trash_Schedule_Website" "$WEB_ROOT"

if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
    scheme=https
    render "$SRC_DIR/deploy/nginx-tls.conf" > "$TMP_DIR/site.conf"
else
    scheme=http
    echo "No TLS certificate at $SSL_CERT, serving plain HTTP for now."
    render "$SRC_DIR/deploy/nginx-http.conf" > "$TMP_DIR/site.conf"
fi

site_backup=""
if [ -f "$NGINX_SITE" ] && ! cmp -s "$TMP_DIR/site.conf" "$NGINX_SITE"; then
    site_backup="$NGINX_SITE.bak.$(date +%Y%m%d%H%M%S)"
    cp -p "$NGINX_SITE" "$site_backup"
    echo "Previous nginx site saved as $site_backup"
fi
cp "$TMP_DIR/site.conf" "$NGINX_SITE"
ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/trashschedulenj
rm -f /etc/nginx/sites-enabled/default
if ! nginx -t; then
    [ -n "$site_backup" ] && cp -p "$site_backup" "$NGINX_SITE"
    fail "The new nginx configuration is not valid. The previous site file was put back."
fi
systemctl reload nginx

# -------------------------------------------------------------- self check
step "Checking the installation"
test_address='{"key":"19 ABERDEEN RD 07208"}'
answer=""
for _ in $(seq 1 20); do
    answer="$(curl -s -m 5 -X POST -H 'Content-Type: application/json' -d "$test_address" http://127.0.0.1:5000/data || true)"
    [ -n "$answer" ] && break
    sleep 1
done
[ -n "$answer" ] || fail "$SERVICE is not answering on port 5000. See: journalctl -u $SERVICE -n 50"
echo "Python server answered: $answer"

site_code="$(curl -sk -m 5 -o /dev/null -w '%{http_code}' "$scheme://127.0.0.1/" || true)"
proxy_answer="$(curl -sk -m 5 -X POST -H 'Content-Type: application/json' -d "$test_address" "$scheme://127.0.0.1/data" || true)"
echo "nginx home page status: $site_code"
echo "nginx /data answered:   $proxy_answer"
[ "$site_code" = "200" ] || fail "nginx did not serve the home page. See: /var/log/nginx/error.log"
[ "$proxy_answer" = "$answer" ] || fail "nginx did not pass /data through to the Python server."
config_answer="$(curl -sk -m 5 "$scheme://127.0.0.1/config" || true)"
case "$config_answer" in
    *'"towns"'*) echo "nginx /config answered:  ok" ;;
    *) fail "nginx did not pass /config through to the Python server." ;;
esac
if [ -n "$MAPS_KEY" ]; then
    echo "Google Maps address search: on"
else
    echo "Google Maps address search: off (no key). To turn it on: sudo GOOGLE_MAPS_API_KEY='...' ./install.sh"
fi

printf '\nTrashScheduleNJ is installed and running (%s).\n' "$scheme"
