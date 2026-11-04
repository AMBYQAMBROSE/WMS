#!/usr/bin/env bash
# Upgrade: run inside the extracted **new version** offline package directory  bash upgrade.sh --dir /opt/wms
# Flow: verify -> import images -> back up database -> switch version -> migrate -> add base data -> start -> readiness check; any failed step rolls back automatically.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "$0")/scripts/lib.sh"
PKG_DIR=$(abspath "$(dirname "$0")")

WMS_DIR=/opt/wms YES=0
while [ $# -gt 0 ]; do
  case $1 in
    --dir) WMS_DIR=$2; shift 2 ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) echo "Usage: bash upgrade.sh --dir INSTALL_DIR [-y]"; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done
[ -f "$WMS_DIR/.env" ] || die "$WMS_DIR is not an install directory (no .env)"
WMS_DIR=$(abspath "$WMS_DIR")

START=$(date +%s)
NEW=$(cat "$PKG_DIR/VERSION")
OLD=$(current_version)
[ "$NEW" != "$OLD" ] || die "Already at $NEW; nothing to upgrade"
if [ "$(printf '%s\n%s\n' "$OLD" "$NEW" | sort -V | head -n1)" != "$OLD" ]; then
  die "Package version $NEW is older than the current $OLD; to go back to an old version use scripts/rollback.sh"
fi

require_docker
log "Verifying package"
(cd "$PKG_DIR" && sha256sum -c --quiet SHA256SUMS) || die "Package checksum failed; copy the package again"
log "Pre-upgrade check: current version $OLD must be running normally"
wait_ready 30 || die "The current system is unhealthy; fix it before upgrading (nothing was changed)"

if [ "$YES" != 1 ]; then
  printf 'Upgrade %s from %s to %s; services will be down for a few minutes. Continue? [y/N] ' "$WMS_DIR" "$OLD" "$NEW"
  read -r answer
  [ "$answer" = y ] || [ "$answer" = Y ] || die "Cancelled"
fi

log "Importing new version images"
for f in "$PKG_DIR"/images/*.tar.gz; do
  docker load -i "$f" | sed 's/^/  /'
done

log "Stopping services (database keeps running), backing up database"
stop_app
LABEL="pre-upgrade-${OLD}-to-${NEW}-$(date +%Y%m%d%H%M%S)"
BACKUP_FILE=$(backup_db "$LABEL") || { dc up -d; die "Backup failed; original services restored, nothing was changed"; }
log "Backed up: $BACKUP_FILE"

# Save what rollback needs first, so any later failed step can be undone
cp "$WMS_DIR/docker-compose.yml" "$WMS_DIR/state/docker-compose.$OLD.yml"
cat >"$WMS_DIR/state/last-upgrade" <<EOF
FROM_VERSION=$OLD
TO_VERSION=$NEW
BACKUP_FILE=$BACKUP_FILE
STARTED_AT=$(date '+%F %T')
EOF

rollback_now() {
  warn "Upgrade failed, rolling back to $OLD automatically"
  bash "$WMS_DIR/scripts/rollback.sh" --dir "$WMS_DIR" --yes || die "Automatic rollback failed too; leave the system as is and contact your implementation contact (backup: $BACKUP_FILE)"
  die "Upgrade failed and rolled back to $OLD; send the log above to your implementation contact"
}
# Check every step explicitly and roll back on failure. No trap ERR: when the failure happens inside a function (e.g. backend_run),
# set -e exits without firing the ERR trap and services are left half-upgraded (this actually happened in testing)
step() { "$@" || rollback_now; }

log "Switching to $NEW"
step cp "$PKG_DIR/docker-compose.yml" "$PKG_DIR/VERSION" "$WMS_DIR/"
step cp "$PKG_DIR"/scripts/*.sh "$WMS_DIR/scripts/"
step env_set WMS_VERSION "$NEW"

log "Database migration"
step backend_run alembic upgrade head
log "Adding base data for the new version, such as permissions (existing settings are not overwritten)"
step backend_run python -m scripts.seed

log "Starting services"
step dc up -d
step wait_ready 180

ELAPSED=$(($(date +%s) - START))
printf '%s upgrade %s -> %s elapsed=%ss backup=%s\n' "$(date '+%F %T')" "$OLD" "$NEW" "$ELAPSED" "$BACKUP_FILE" >>"$WMS_DIR/logs/deploy.log"
log "Upgrade complete: $OLD -> $NEW (took ${ELAPSED}s). If you find a serious problem run bash $WMS_DIR/scripts/rollback.sh --dir $WMS_DIR"
