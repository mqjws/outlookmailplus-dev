#!/bin/sh
set -eu

if [ "$(id -u)" -ne 1001 ]; then
    echo "Run as ubuntu: sh deploy/backup.sh" >&2
    exit 1
fi

cd /home/ubuntu/apps/outlook-email-plus
if [ "$(pwd -P)" != /home/ubuntu/apps/outlook-email-plus ]; then
    echo "Unexpected deployment path" >&2
    exit 1
fi
test -f compose.production.yaml
test -f .env.production
test -f data/outlook_accounts.db
container_id=$(sudo -n docker compose -f compose.production.yaml ps -q app)
if [ -z "$container_id" ]; then
    echo "The app must be running before this backup" >&2
    exit 1
fi

umask 077
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="backups/outlook-$stamp.tar.gz"
test ! -e "$backup"

trap 'sudo -n docker compose -f compose.production.yaml start app' EXIT
sudo -n docker compose -f compose.production.yaml stop app
tar -czf "$backup.partial" data .runtime .env.production compose.production.yaml
mv "$backup.partial" "$backup"
chmod 600 "$backup"
echo "Backup saved to /home/ubuntu/apps/outlook-email-plus/$backup"
echo "Contains credentials. Download securely and retain the corresponding image."
