#!/usr/bin/env bash
# Roll back the last upgrade: restore the pre-upgrade database backup and switch back to the old image version.
#   bash scripts/rollback.sh --dir /opt/wms
# Note: business data created after the upgrade is lost with the database restore; use only when a problem is found right after upgrading.
set -euo pipefail
WMS_DIR=/opt/wms YES=0
while [ $# -gt 0 ]; do
  case $1 in
    --dir) WMS_DIR=$2; shift 2 ;;
    -y|--yes) YES=1; shift ;;
    *) echo "Usage: bash rollback.sh --dir INSTALL_DIR [-y]"; exit 1 ;;
  esac
done
# shellcheck source=lib.sh
. "$WMS_DIR/scripts/lib.sh"
WMS_DIR=$(abspath "$WMS_DIR")

STATE="$WMS_DIR/state/last-upgrade"
[ -f "$STATE" ] || die "No upgrade record to roll back ($STATE)"
FROM_VERSION=$(grep '^FROM_VERSION=' "$STATE" | cut -d= -f2-)
TO_VERSION=$(grep '^TO_VERSION=' "$STATE" | cut -d= -f2-)
BACKUP_FILE=$(grep '^BACKUP_FILE=' "$STATE" | cut -d= -f2-)
PREV_COMPOSE="$WMS_DIR/state/docker-compose.$FROM_VERSION.yml"

docker image inspect "wms-backend:$FROM_VERSION" "wms-web:$FROM_VERSION" >/dev/null 2>&1 \
  || die "Old image version $FROM_VERSION is not on this host (cleaned up?); import the images from the $FROM_VERSION offline package, then roll back"

if [ "$YES" != 1 ]; then
  printf 'Roll back to %s and overwrite the database with %s (business data since %s will be lost). Continue? [y/N] ' "$FROM_VERSION" "$BACKUP_FILE" "$TO_VERSION"
  read -r answer
  [ "$answer" = y ] || [ "$answer" = Y ] || die "Cancelled"
fi

START=$(date +%s)
log "Stopping services"
stop_app || true

log "Switching back to $FROM_VERSION"
[ -f "$PREV_COMPOSE" ] && cp "$PREV_COMPOSE" "$WMS_DIR/docker-compose.yml"
env_set WMS_VERSION "$FROM_VERSION"
printf '%s\n' "$FROM_VERSION" >"$WMS_DIR/VERSION"

start_db
log "Restoring database: $BACKUP_FILE"
backend_run python -m scripts.dbops restore "$BACKUP_FILE"

# The old version may lack services only the new version has (e.g. worker); remove them too
dc up -d --remove-orphans
wait_ready 180 || die "Services not ready after rollback; contact your implementation contact"
mv "$STATE" "$STATE.rolled-back-$(date +%Y%m%d%H%M%S)"
printf '%s rollback %s -> %s elapsed=%ss backup=%s\n' "$(date '+%F %T')" "$TO_VERSION" "$FROM_VERSION" \
  "$(($(date +%s) - START))" "$BACKUP_FILE" >>"$WMS_DIR/logs/deploy.log"
log "Rolled back to $FROM_VERSION"
