#!/usr/bin/env bash
#
# Update the live TrashScheduleNJ site from GitHub.
#
#   cd TrashScheduleNJ
#   ./update.sh
#
# Pulls the latest commits for the branch this checkout is on, then runs
# install.sh, which copies the code into place, rebuilds the Python environment
# and restarts the python_server service. Run it as your normal user: it asks
# for sudo only for the install step.
#
# Settings for install.sh are passed through, for example:
#   MYSQL_ROOT_PASSWORD='...' ./update.sh
#   REIMPORT=1 ./update.sh

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SRC_DIR"

fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# git must run as the owner of the checkout, not as root, so that it uses that
# user's GitHub login and does not leave root-owned files in .git
if [ "$(id -u)" -eq 0 ]; then
    [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] \
        || fail "Run update.sh as your normal user, not as root."
    GIT=(sudo -u "$SUDO_USER" git)
    INSTALL=()
else
    GIT=(git)
    INSTALL=(sudo --preserve-env=MYSQL_ROOT_PASSWORD,GOOGLE_MAPS_API_KEY,REIMPORT,INSTALL_DIR,SERVER_NAME,SSL_CERT,SSL_KEY)
fi

branch="$("${GIT[@]}" rev-parse --abbrev-ref HEAD)"
[ "$branch" != HEAD ] || fail "This checkout is not on a branch. Run: git checkout <branch>"

if [ -n "$("${GIT[@]}" status --porcelain --untracked-files=no)" ]; then
    "${GIT[@]}" status --short --untracked-files=no
    fail "There are uncommitted changes. Commit them or undo them, then run update.sh again."
fi

printf '==> Pulling %s from GitHub\n' "$branch"
before="$("${GIT[@]}" rev-parse HEAD)"
"${GIT[@]}" pull --ff-only
after="$("${GIT[@]}" rev-parse HEAD)"
if [ "$before" = "$after" ]; then
    echo "Already up to date, reinstalling the current version."
else
    "${GIT[@]}" log --oneline "$before..$after"
fi

# exec so that the new install.sh from the pull is the one that runs
exec "${INSTALL[@]}" "$SRC_DIR/install.sh"
