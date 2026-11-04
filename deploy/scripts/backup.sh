#!/usr/bin/env bash
# Manual/scheduled backup: bash scripts/backup.sh --dir /opt/wms [--keep 14]
# Scheduled job example (daily at 2:00, keep 14 copies):
#   0 2 * * * bash /opt/wms/scripts/backup.sh --dir /opt/wms --keep 14 >> /opt/wms/logs/backup.log 2>&1
# When the customer's DBA already has a backup policy this is only a supplement (COPY_ONLY, does not break the DBA's backup chain).
set -euo pipefail
WMS_DIR=/opt/wms KEEP=0
while [ $# -gt 0 ]; do
  case $1 in
    --dir) WMS_DIR=$2; shift 2 ;;
    --keep) KEEP=$2; shift 2 ;;
    *) echo "Usage: bash backup.sh --dir INSTALL_DIR [--keep COPIES]"; exit 1 ;;
  esac
done
# shellcheck source=lib.sh
. "$WMS_DIR/scripts/lib.sh"
WMS_DIR=$(abspath "$WMS_DIR")

FILE=$(backup_db "manual-$(current_version)-$(date +%Y%m%d%H%M%S)")
log "Backed up: $FILE"

# Cleanup applies only to the bundled database (files in backups/ on this host); with your own SQL Server the files live on the database server and the DBA manages them
if [ "$KEEP" -gt 0 ] && bundled_db; then
  # Pre-upgrade backups are the basis for rollback and are never cleaned up
  ls -1t "$WMS_DIR"/backups/manual-*.bak 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old" && log "Removed old backup $(basename "$old")"
  done
fi
