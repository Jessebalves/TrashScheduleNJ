#!/usr/bin/env bash
#
# TrashScheduleNJ uninstaller. Undoes what install.sh set up.
#
#   sudo ./uninstall.sh              asks before removing anything
#   sudo DRY_RUN=1 ./uninstall.sh    only shows what would be removed
#   sudo YES=1 ./uninstall.sh        no question (for scripts)
#
# What it removes:
#   - the python_server systemd service
#   - the nginx site (and puts the stock "default" site back if no other
#     site is left enabled)
#   - the web root symlink /var/www/trashschedulenj
#   - the code ($INSTALL_DIR/app) and the Python venv ($INSTALL_DIR/venv)
#   - /etc/trashschedulenj (database credentials, Google Maps key, data checksum)
#   - the MySQL database `trashschedule` and the MySQL user `trashschedule`
#
# What it keeps unless asked:
#   KEEP_DATABASE=1    keep the MySQL database and user
#   REMOVE_PACKAGES=1  also purge nginx and mysql-server with apt. This deletes
#                      ALL MySQL databases on the server and any other nginx
#                      sites, so only use it on a server that runs nothing else.
#
# What it never touches:
#   - python3, curl, openssl, ca-certificates, tzdata (Ubuntu itself needs them)
#   - the TLS certificate and key (install.sh does not create them)
#   - backups install.sh made: /var/www/trashschedulenj.bak.* and
#     /etc/nginx/sites-available/trashschedulenj.bak.* (listed at the end)
#   - anything else in $INSTALL_DIR that install.sh did not create
#   - this git checkout
#
# MySQL admin access works as in install.sh: socket login for root, or
#   sudo MYSQL_ROOT_PASSWORD='...' ./uninstall.sh
# or type the password when asked.
#
# Use the same INSTALL_DIR as for install.sh if it was changed:
#   INSTALL_DIR=/trashschedulenj

set -euo pipefail
umask 022

INSTALL_DIR="${INSTALL_DIR:-/trashschedulenj}"
APP_DIR="$INSTALL_DIR/app"
VENV_DIR="$INSTALL_DIR/venv"
ENV_DIR=/etc/trashschedulenj
WEB_ROOT=/var/www/trashschedulenj
DB_NAME=trashschedule
DB_USER=trashschedule
SERVICE=python_server
SERVICE_FILE="/etc/systemd/system/$SERVICE.service"
NGINX_SITE=/etc/nginx/sites-available/trashschedulenj
NGINX_ENABLED=/etc/nginx/sites-enabled/trashschedulenj
NGINX_DEFAULT=/etc/nginx/sites-available/default
DRY_RUN="${DRY_RUN:-0}"
YES="${YES:-0}"
KEEP_DATABASE="${KEEP_DATABASE:-0}"
REMOVE_PACKAGES="${REMOVE_PACKAGES:-0}"
PACKAGES=(nginx nginx-common 'mysql-server*' 'mysql-client*' mysql-common)

TMP_DIR=""
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
cleanup() { [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR"; return 0; }
trap cleanup EXIT

# Run a command, or only print it with DRY_RUN=1
run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf '  would run: %s\n' "$*"
    else
        "$@"
    fi
}

[ "$(id -u)" -eq 0 ] || fail "Run this script with sudo: sudo ./uninstall.sh"
case "$INSTALL_DIR" in
    /*) ;;
    *) fail "INSTALL_DIR must be an absolute path." ;;
esac
[ "$INSTALL_DIR" != "/" ] || fail "INSTALL_DIR must not be /."
TMP_DIR="$(mktemp -d)"

have() { command -v "$1" >/dev/null 2>&1; }
mysql_running() { have mysql && systemctl is-active --quiet mysql; }

# ------------------------------------------------------------ confirmation
echo "This removes TrashScheduleNJ from this server:"
echo "  - systemd service  $SERVICE ($SERVICE_FILE)"
echo "  - nginx site       $NGINX_SITE"
echo "  - web root link    $WEB_ROOT"
echo "  - code and venv    $APP_DIR, $VENV_DIR"
echo "  - settings         $ENV_DIR (database password, Google Maps key)"
if [ "$KEEP_DATABASE" = "1" ]; then
    echo "  - MySQL database   kept (KEEP_DATABASE=1)"
else
    echo "  - MySQL database   \`$DB_NAME\` and user '$DB_USER'@'localhost'"
fi
if [ "$REMOVE_PACKAGES" = "1" ]; then
    echo "  - apt packages     nginx and mysql-server, PURGED with ALL their data and sites"
fi
if [ "$DRY_RUN" = "1" ]; then echo "(dry run: nothing will be changed)"; fi

if [ "$DRY_RUN" != "1" ] && [ "$YES" != "1" ]; then
    [ -t 0 ] || fail "Not asking without a terminal. Run: sudo YES=1 ./uninstall.sh"
    read -r -p "Continue? Type 'yes': " answer
    [ "$answer" = "yes" ] || fail "Nothing was removed."
fi

# ----------------------------------------------------------------- service
step "Removing the $SERVICE service"
if systemctl list-unit-files "$SERVICE.service" 2>/dev/null | grep -q "^$SERVICE.service"; then
    run systemctl disable --now "$SERVICE" || echo "WARNING: could not stop $SERVICE, continuing."
fi
if [ -e "$SERVICE_FILE" ]; then
    run rm -f "$SERVICE_FILE"
    run systemctl daemon-reload
    run systemctl reset-failed "$SERVICE" 2>/dev/null || true
else
    echo "Not installed."
fi

# ------------------------------------------------------------------- nginx
step "Removing the nginx site"
removed_site=0
for f in "$NGINX_ENABLED" "$NGINX_SITE"; do
    if [ -e "$f" ] || [ -L "$f" ]; then
        run rm -f "$f"
        removed_site=1
    fi
done
[ "$removed_site" = "1" ] || echo "Not installed."

# install.sh removed the stock default site; put it back if nothing else is enabled
if [ -d /etc/nginx/sites-enabled ] \
   && [ -z "$(find /etc/nginx/sites-enabled -mindepth 1 ! -path "$NGINX_ENABLED" -print -quit)" ]; then
    if [ -f "$NGINX_DEFAULT" ]; then
        echo "No other nginx site is enabled, enabling the stock default site again"
        run ln -sfn "$NGINX_DEFAULT" /etc/nginx/sites-enabled/default
    else
        echo "No nginx site is left enabled (there is no stock default site to put back),"
        echo "so nginx keeps running but serves nothing until a site is added."
    fi
fi

if [ "$REMOVE_PACKAGES" != "1" ] && have nginx && systemctl is-active --quiet nginx; then
    if [ "$DRY_RUN" = "1" ]; then
        echo "  would run: nginx -t && systemctl reload nginx"
    elif nginx -t; then
        systemctl reload nginx
    else
        echo "WARNING: the remaining nginx configuration is not valid, nginx was not reloaded."
    fi
fi

if [ -L "$WEB_ROOT" ]; then
    run rm -f "$WEB_ROOT"
elif [ -e "$WEB_ROOT" ]; then
    echo "WARNING: $WEB_ROOT is not the symlink install.sh makes, leaving it alone."
fi

# -------------------------------------------------------------------- code
step "Removing the code and the Python environment"
for d in "$APP_DIR" "$APP_DIR.new" "$VENV_DIR"; do
    if [ -e "$d" ]; then run rm -rf "$d"; fi
done
if [ -d "$INSTALL_DIR" ]; then
    # What is left once app, app.new and venv are gone
    left="$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
              ! -path "$APP_DIR" ! -path "$APP_DIR.new" ! -path "$VENV_DIR" -printf '  %f\n')"
    if [ -z "$left" ]; then
        run rmdir "$INSTALL_DIR"
    else
        echo "Keeping $INSTALL_DIR, install.sh did not create what is left in it:"
        printf '%s\n' "$left"
    fi
fi

# ---------------------------------------------------------------- database
step "Removing the MySQL database and user"
if [ "$KEEP_DATABASE" = "1" ]; then
    echo "Kept (KEEP_DATABASE=1)."
elif [ "$DRY_RUN" = "1" ]; then
    echo "  would run: DROP DATABASE IF EXISTS \`$DB_NAME\`; DROP USER IF EXISTS '$DB_USER'@'localhost';"
elif ! mysql_running; then
    echo "WARNING: MySQL is not running, the database \`$DB_NAME\` and user '$DB_USER' were not removed."
else
    MYSQL=(mysql --protocol=socket -uroot)
    if ! "${MYSQL[@]}" -e 'SELECT 1' >/dev/null 2>&1; then
        if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then
            [ -t 0 ] || fail "MySQL root needs a password. Run: sudo MYSQL_ROOT_PASSWORD='...' ./uninstall.sh"
            read -r -s -p "MySQL root password: " MYSQL_ROOT_PASSWORD
            echo
        fi
        escaped="${MYSQL_ROOT_PASSWORD//\\/\\\\}"
        escaped="${escaped//\"/\\\"}"
        (umask 077; printf '[client]\nuser=root\npassword="%s"\n' "$escaped" > "$TMP_DIR/admin.cnf")
        MYSQL=(mysql --defaults-extra-file="$TMP_DIR/admin.cnf")
        "${MYSQL[@]}" -e 'SELECT 1' >/dev/null 2>&1 || fail "Could not log in to MySQL as root with that password."
    fi
    "${MYSQL[@]}" <<SQL
DROP DATABASE IF EXISTS \`$DB_NAME\`;
DROP USER IF EXISTS '$DB_USER'@'localhost';
SQL
    echo "Dropped database \`$DB_NAME\` and user '$DB_USER'@'localhost'."
fi

# ------------------------------------------------------------------ config
# Removed after the database step, so a failed MySQL login leaves the
# credentials in place for another try.
step "Removing $ENV_DIR"
if [ -e "$ENV_DIR" ]; then
    run rm -rf "$ENV_DIR"
else
    echo "Not there."
fi

# ---------------------------------------------------------------- packages
if [ "$REMOVE_PACKAGES" = "1" ]; then
    step "Purging nginx and mysql-server"
    export DEBIAN_FRONTEND=noninteractive
    installed=()
    for pkg in $(dpkg-query -W -f='${Package}\n' "${PACKAGES[@]}" 2>/dev/null); do
        if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'ok installed$'; then
            installed+=("$pkg")
        fi
    done
    if [ "${#installed[@]}" -gt 0 ]; then
        run apt-get purge -y -q "${installed[@]}"
        run apt-get autoremove -y -q
    else
        echo "Not installed."
    fi
fi

# ------------------------------------------------------------------ report
backups="$(ls -d "$WEB_ROOT".bak.* "$NGINX_SITE".bak.* 2>/dev/null || true)"
if [ -n "$backups" ]; then
    echo
    echo "Backups made by install.sh were kept. Delete them by hand if not needed:"
    printf '%s\n' "$backups" | sed 's/^/  /'
fi

if [ "$DRY_RUN" = "1" ]; then
    printf '\nDry run finished, nothing was changed.\n'
else
    printf '\nTrashScheduleNJ has been removed.\n'
fi
