# Shared functions for the deployment scripts. Sourced by install / upgrade / rollback / backup / status; not run directly.
# shellcheck shell=bash

set -euo pipefail
# Git Bash on Windows rewrites arguments like /var/... into Windows paths; this variable has no effect on Linux
export MSYS_NO_PATHCONV=1

# Absolute path of a directory. In Git Bash on Windows returns the D:/x form (understood by bash and docker.exe); plain pwd on Linux
abspath() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }

log()  { printf '\033[1;34m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

# Random hex string; avoids tr|head (under pipefail, head closing the pipe early makes the script think it failed)
random_hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }

require_docker() {
  command -v docker >/dev/null || die "Docker is not installed"
  docker info >/dev/null 2>&1 || die "Docker is not running, or the current user lacks permission (join the docker group or use sudo)"
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 plugin (docker compose) is missing"
  local v
  v=$(docker compose version --short | sed 's/^v//')
  # depends_on.required needs 2.20 or later
  if [ "$(printf '%s\n2.20.0\n' "$v" | sort -V | head -n1)" != "2.20.0" ]; then
    die "Docker Compose is too old ($v); 2.20 or later is required"
  fi
}

env_get() {
  # Read a value from .env; empty when the key is missing
  local line
  line=$(grep -E "^$1=" "$WMS_DIR/.env" | tail -n1 || true)
  printf '%s' "${line#*=}"
}

env_set() {
  local key=$1 value=$2 file="$WMS_DIR/.env"
  if grep -qE "^$key=" "$file"; then
    # Use | as the delimiter and escape \ & | in the value
    local escaped
    escaped=$(printf '%s' "$value" | sed 's/[\\&|]/\\&/g')
    sed -i "s|^$key=.*|$key=$escaped|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

dc() {
  docker compose --project-directory "$WMS_DIR" -f "$WMS_DIR/docker-compose.yml" \
    -p "$(env_get COMPOSE_PROJECT_NAME)" "$@"
}

# Run a command in a one-off backend container (migration, seed data, backup/restore) without affecting running services
backend_run() { dc run --rm -T --no-deps backend "$@"; }

# Stop the application services (not the database). Only stop services in the current compose file: older versions may have no worker
stop_app() {
  local services
  services=$(dc config --services | grep -xE 'web|worker|backend' | tr '
' ' ')
  # shellcheck disable=SC2086
  [ -z "$services" ] || dc stop $services
}

bundled_db() { [ "$(env_get COMPOSE_PROFILES)" = "bundled-db" ]; }

start_db() {
  if bundled_db; then
    log "Starting database container"
    dc up -d --wait db
  fi
  backend_run python -m scripts.dbops wait --timeout 180
}

# Wait for the backend to be ready (schema version matches the code) and check that the web reverse proxy reaches the backend
wait_ready() {
  local timeout=${1:-180} deadline body
  deadline=$(($(date +%s) + timeout))
  while :; do
    if body=$(dc exec -T web wget -qO- http://127.0.0.1/api/v1/health/ready 2>/dev/null); then
      log "Services ready: $body"
      return 0
    fi
    [ "$(date +%s)" -lt "$deadline" ] || {
      warn "Timed out waiting for readiness; recent logs:"
      dc logs --tail 40 backend web >&2 || true
      return 1
    }
    sleep 3
  done
}

current_version() { env_get WMS_VERSION; }

backup_db() {
  # Print the backup file's full path on the database server
  backend_run python -m scripts.dbops backup "$1" | tail -n1 | tr -d '\r'
}
