#!/usr/bin/env bash
# Show running status: bash scripts/status.sh --dir /opt/wms
set -euo pipefail
WMS_DIR=/opt/wms
[ "${1:-}" = --dir ] && WMS_DIR=$2
# shellcheck source=lib.sh
. "$WMS_DIR/scripts/lib.sh"
WMS_DIR=$(abspath "$WMS_DIR")

echo "Install directory: $WMS_DIR"
echo "Configured version: $(current_version)    Database: $(bundled_db && echo bundled SQL Server || echo customer SQL Server)"
echo
dc ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
echo
if body=$(dc exec -T web wget -qO- http://127.0.0.1/api/v1/health/ready 2>/dev/null); then
  echo "Readiness: $body"
else
  echo "Readiness: not ready (see docker compose logs backend)"
fi
echo
echo "Recent deployments:"
tail -n 5 "$WMS_DIR/logs/deploy.log" 2>/dev/null || echo "(none)"
