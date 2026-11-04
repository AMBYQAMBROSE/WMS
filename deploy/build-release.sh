#!/usr/bin/env bash
# Build the offline install package (run on a build machine with Docker and internet access):
#   bash deploy/build-release.sh [--with-db] [--version 1.2.0]
# Produces deploy/dist/wms-<version>.tar.gz; copy it to the customer server, extract, then run install.sh / upgrade.sh.
# --with-db: also bundle the SQL Server image (about 1.5GB), needed when the customer has no SQL Server of their own.
set -euo pipefail
export MSYS_NO_PATHCONV=1
# In Git Bash on Windows use the D:/x form, which docker.exe understands
ROOT=$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })
VERSION=$(tr -d ' \r\n' <"$ROOT/VERSION")
WITH_DB=0
MSSQL_IMAGE=mcr.microsoft.com/mssql/server:2022-latest
while [ $# -gt 0 ]; do
  case $1 in
    --with-db) WITH_DB=1; shift ;;
    --version) VERSION=$2; shift 2 ;;
    *) echo "Usage: bash deploy/build-release.sh [--with-db] [--version X.Y.Z]"; exit 1 ;;
  esac
done

if [ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]; then
  echo "[WARN] The working tree has uncommitted changes and the package will include them; commit and tag before an official release" >&2
fi

OUT="$ROOT/deploy/dist/wms-$VERSION"
rm -rf "$OUT" && mkdir -p "$OUT/images" "$OUT/scripts" "$OUT/docs"

echo "== Building images $VERSION"
docker build --build-arg APP_VERSION="$VERSION" -t "wms-backend:$VERSION" "$ROOT/apps/backend"
docker build --build-arg APP_VERSION="$VERSION" -t "wms-web:$VERSION" "$ROOT/apps/web"

echo "== Exporting images"
docker save "wms-backend:$VERSION" "wms-web:$VERSION" | gzip -6 >"$OUT/images/wms-$VERSION.tar.gz"
if [ "$WITH_DB" = 1 ]; then
  docker image inspect "$MSSQL_IMAGE" >/dev/null 2>&1 || docker pull "$MSSQL_IMAGE"
  docker save "$MSSQL_IMAGE" | gzip -6 >"$OUT/images/mssql-2022.tar.gz"
fi

echo "== Assembling package"
cp "$ROOT/deploy/install.sh" "$ROOT/deploy/upgrade.sh" "$ROOT/deploy/docker-compose.yml" "$ROOT/deploy/env.template" "$OUT/"
cp "$ROOT"/deploy/scripts/*.sh "$OUT/scripts/"
cp "$ROOT/docs/deployment.md" "$ROOT/docs/integration.md" "$OUT/docs/"
printf '%s\n' "$VERSION" >"$OUT/VERSION"
# Strip CRLF when packaging on Windows, or bash on Linux fails with $'\r': command not found
sed -i 's/\r$//' "$OUT"/*.sh "$OUT"/scripts/*.sh "$OUT/docker-compose.yml" "$OUT/env.template"
chmod +x "$OUT"/*.sh "$OUT"/scripts/*.sh

(cd "$OUT" && find . -type f ! -name SHA256SUMS | sort | xargs sha256sum >SHA256SUMS)

# Use a relative path: GNU tar treats an archive name with a colon such as D:/x as a remote host
(cd "$ROOT/deploy/dist" && tar -czf "wms-$VERSION.tar.gz" "wms-$VERSION" && sha256sum "wms-$VERSION.tar.gz" >"wms-$VERSION.tar.gz.sha256")
echo "== Done: deploy/dist/wms-$VERSION.tar.gz ($(du -h "$ROOT/deploy/dist/wms-$VERSION.tar.gz" | cut -f1))"
