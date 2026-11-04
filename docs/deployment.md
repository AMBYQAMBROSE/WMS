# On-Prem Deployment Runbook (SOP)

For implementation engineers and customer IT operations. Each customer gets its own isolated environment on their internal network; installing and upgrading need no internet access at any point.

## 1. Deliverables

One offline install package `wms-<version>.tar.gz` (with a `.sha256` checksum file). After extracting:

| File | Purpose |
|---|---|
| `install.sh` | First install |
| `upgrade.sh` | Upgrade (run from the new version's package) |
| `scripts/rollback.sh` | Roll back the last upgrade |
| `scripts/backup.sh` | Manual / scheduled database backup |
| `scripts/status.sh` | Show running status |
| `docker-compose.yml`, `env.template` | Service orchestration, settings template |
| `images/` | Docker images (imported offline); packages with `mssql-2022.tar.gz` include SQL Server |
| `SHA256SUMS` | File checksums, verified automatically before install/upgrade |

The system runs as 4 containers:
- `web`: nginx serving the web console and reverse-proxying `/api`
- `backend`: FastAPI
- `worker`: pushes document events to external systems; same image as backend
- `db`: SQL Server (optional)

Browsers and PDAs only use one port, on `web`. The database exposes no ports.

## 2. Server requirements

| Item | Requirement |
|---|---|
| OS | Linux x86_64 (CentOS Stream / RHEL 8+, Ubuntu 20.04+, or any distribution that runs Docker) |
| Docker | Docker Engine 24+, Docker Compose plugin **2.20+** (check with `docker compose version`) |
| CPU / memory | Minimum 4 cores / 8GB. The bundled SQL Server needs at least 2GB of its own. Recommended: 8 cores / 16GB |
| Disk | At least 20GB for the system. Size data and backups by business volume; at least 100GB is recommended, ideally with backups on a separate disk |
| Network | One HTTP port open to the internal network (default 80); no internet needed |
| Other | `bash`, `sha256sum`, `tar` (included in the distribution) |

### Choose a database

**Bundled SQL Server (default)**
- Use a package built with `--with-db`.
- Runs as **Express edition** by default (free, 10GB per database limit).
- With a customer license, install with `--mssql-pid Standard` (or `Enterprise`, or a product key).
- **Confirm SQL Server licensing before production use.**

**Customer's own SQL Server** (common at large companies, managed centrally by DBAs)
- SQL Server 2017 or later. Ask the DBA to prepare:
  - **A login** with `db_owner` on the application database.
    - The DBA can create the database in advance. Use a case-insensitive collation; the install script uses `Chinese_PRC_CI_AS`, and `Latin1_General_CI_AS` also works because all text columns are Unicode.
    - Otherwise the login needs `dbcreator` so the install script can create it.
  - **Backup and restore rights**:
    - `db_backupoperator` for the automatic pre-upgrade backup.
    - **Rollback restores the database**, which needs `dbcreator` or `sysadmin`. Without these the DBA restores manually; see 7.2.
  - **A backup directory** on the database server that the SQL Server service account can write to (install option `--backup-dir`).
  - **Network access** from the WMS server to the database server on port 1433 (or the actual port).
    - **Named instances need a fixed TCP port.** Write `host:port` in the connection string; `host\instance` does not work from inside a container.

## 3. Packaging (on the build machine, by developers)

The build machine needs Docker and internet access (to pull base images). From the repository root:

```bash
# 1. Set the version (semantic versioning, only ever increases)
echo 1.0.0 > VERSION
git commit -am "release 1.0.0" && git tag v1.0.0

# 2. Package; add --with-db when the customer has no SQL Server of their own (about 700MB with it, about 100MB without)
bash deploy/build-release.sh --with-db
# Produces deploy/dist/wms-1.0.0.tar.gz and .sha256
```

The script warns when the working tree has uncommitted changes. Official releases must be packaged from a tagged commit.

## 4. First install

```bash
# Copy the package to the server, verify and extract
sha256sum -c wms-1.0.0.tar.gz.sha256
tar -xzf wms-1.0.0.tar.gz && cd wms-1.0.0

# Bundled SQL Server
sudo bash install.sh --dir /opt/wms --company "Acme Group East DC" --preset distribution --http-port 80

# Or: the customer's own SQL Server (wrap the whole connection string in single quotes)
sudo bash install.sh --dir /opt/wms --company "Acme Group East DC" --preset 3pl \
  --external-db 'mssql+pyodbc://wms_app:PASSWORD@10.0.0.5:1433/wms?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes' \
  --backup-dir 'D:\SQLBackup\wms'
```

Common options (`bash install.sh --help` lists them all):

| Option | Description |
|---|---|
| `--dir` | Install directory for the `.env` settings, backups, state and logs. All later operations use this directory |
| `--preset` | Industry preset: decides the features enabled by default, preset roles, units of measure and reason codes; see section 5 |
| `--company` / `--tenant-code` | Company name, tenant code |
| `--http-port` | Access port |
| `--project` | Use different names (and ports) to install several instances on one server, e.g. test + production |
| `--admin-password` | Initial admin password; randomly generated if omitted |

The install script, in order:
1. Verifies the package and imports the images.
2. Generates `.env`, with a random database password and token signing key.
3. Starts the database, creates it and creates the tables.
4. Loads the preset, starts the services and runs the readiness check.

If it fails partway, it prints the cleanup commands; after cleaning up you can reinstall directly.

### Post-install checklist

1. Open `http://<server IP>:<port>` in a browser and sign in as `admin` with the password the script printed.
2. Change the admin password (top right), then delete `/opt/wms/state/initial-admin-password`.
3. System → Feature flags: confirm the extension modules for the customer's business.
4. System → Roles: adjust the preset roles to the customer's jobs, then create users.
5. Master data: System → Data import, importing from the templates in the order locations → business partners → items. Import opening stock after the full stock count on the day before go-live (see go-live.md).
6. PDA: on the sign-in screen, set "Server URL" to `http://<server IP>:<port>`.
7. Set up scheduled backups (section 8) and do a restore drill.
8. Copy `/opt/wms/.env` to the customer's password vault. The database password exists only there, and if the file is lost, sign-in tokens already issued can no longer be verified.

## 5. Industry presets

Preset files are in the backend image's `presets/` directory (source: `apps/backend/presets/*.json`):

| Preset | For | Features enabled by default | Preset roles |
|---|---|---|---|
| `standard` | General warehouse | None | Warehouse supervisor, warehouse clerk, read-only |
| `distribution` | FMCG distribution, multi-customer delivery | Returns, returnable assets | Above + picker |
| `3pl` | Third-party logistics warehousing | Cross-docking, repacking, returns, allow over-receipt | Above + picker, value-added services operator |

- **Presets are written only the first time.** Existing feature flags and preset roles are not overwritten, so settings the customer changed survive upgrades.
- **To add a preset**, add a JSON file to `presets/`.
  - It can inherit with `"extends": "standard"`.
  - Permissions support wildcards (`*.read`, `grn.*`).
  - Invalid permission codes are reported by the pre-packaging check: `python -m scripts.seed --check`.

## 6. Upgrade

```bash
tar -xzf wms-1.1.0.tar.gz && cd wms-1.1.0
sudo bash upgrade.sh --dir /opt/wms
```

Flow: verify package → check the current system is healthy → import new images → **stop services and back up the database** → switch version → database migration → add the new version's permissions → start → readiness check (the schema version must match the new code).

- **Any failed step rolls back automatically**: the pre-upgrade backup is restored and the old version switched back, so the system returns to its pre-upgrade state.
- **Downtime** is about 1 minute, mostly backup and migration, and grows with data volume. Schedule upgrades outside working hours.
  - Migrations that add indexes take longer with more data (measured: indexing 2.2M document lines took about 15 seconds).
  - With very large data volumes, rehearse in the test environment with a backup of the production database first to estimate the downtime.
- **No downgrades**: the script refuses a package older than the current version. Use rollback to go back.
- **Pre-upgrade backups** are kept in the backup directory as `pre-upgrade-<old>-to-<new>-<time>.bak` and are never cleaned up automatically.
- **From 0.8.0 the database runs with READ_COMMITTED_SNAPSHOT.** The migration enables it automatically and needs exclusive access to the database for a few seconds.
  - With the customer's own SQL Server, tell the DBA in advance: row versions are stored in tempdb, which should be on SSD.

## 7. Rollback

### 7.1 Roll back the last upgrade

```bash
sudo bash /opt/wms/scripts/rollback.sh --dir /opt/wms
```

This restores the pre-upgrade database backup and switches back to the old version. **Business data created after the upgrade is lost.**
- Use it only for serious problems found right after the upgrade, during verification.
- If a problem shows up after a period of normal operation, fix it and release a new version instead of rolling back.

The old version's images must still be on the host (the script checks). Do not run `docker image prune -a` after upgrading.

### 7.2 Without restore rights (customer's own SQL Server)

The DBA restores the database from the pre-upgrade backup (its path is recorded in `/opt/wms/state/last-upgrade`). Then:

```bash
cd /opt/wms
sed -i 's/^WMS_VERSION=.*/WMS_VERSION=<old version>/' .env
cp state/docker-compose.<old version>.yml docker-compose.yml
docker compose -p wms up -d
```

## 8. Backup and restore

```bash
# Manual backup
sudo bash /opt/wms/scripts/backup.sh --dir /opt/wms

# Scheduled backup: daily at 2:00, keep 14 copies (crontab -e)
0 2 * * * bash /opt/wms/scripts/backup.sh --dir /opt/wms --keep 14 >> /opt/wms/logs/backup.log 2>&1
```

- **How backups are made**: with `COPY_ONLY`, then verified (`RESTORE VERIFYONLY`), so they do not break the DBA's own backup chain.
- **Bundled database**: backup files are in `/opt/wms/backups/`. **Copy them to another machine or storage**, or a server disk failure loses the backups too.
- **Customer's own SQL Server**: backup files are under `--backup-dir` on the database server, and the DBA adds them to the existing backup policy.
- **To restore any backup** (this overwrites current data; stop services first):

```bash
cd /opt/wms
docker compose -p wms stop web worker backend
docker compose -p wms run --rm -T --no-deps backend python -m scripts.dbops restore /var/opt/mssql/backup/<file name>.bak
docker compose -p wms up -d
```

## 9. Performance and capacity

For server sizing, SQL Server settings and load-test methods see [performance.md](performance.md). Common settings (`.env`):

| Setting | Default | Description |
|---|---|---|
| `WEB_CONCURRENCY` | 2 | Number of backend processes; set to the CPU core count |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 20 / 20 | Database connections per backend process; total SQL Server connections ≈ processes × 55 |

Document numbers are taken in a separate transaction and are skipped when the business operation fails, so **document numbers can have gaps**.

## 10. Routine operations

| Task | Command (run in the install directory; `-p` takes the `--project` name, default wms) |
|---|---|
| Status | `bash scripts/status.sh --dir /opt/wms` |
| Logs | `docker compose -p wms logs --tail 200 -f backend` |
| Restart | `docker compose -p wms restart backend web` |
| Change settings | Edit `.env`, then `docker compose -p wms up -d` |
| Deployment history (with durations) | `cat logs/deploy.log` |

- **Restarts**: containers restart automatically and come back with Docker after a server reboot (make sure `systemctl enable docker` is set).
- **Logs**: rotated at 20MB × 5 files, so they never fill the disk.

### Monitoring and the audit log

- **System → System health** (needs `system.settings`) shows the database round-trip time and size, whether the background worker is running, the integration queue, schema version and the largest tables. It refreshes itself every 15 seconds and lists anything that needs attention at the top.
- **Request ids**: every API response carries an `X-Request-ID` header, and an unexpected server error shows the id to the user ("Internal server error (request id …)"). Find everything about that request with `docker compose -p wms logs backend | grep <id>`.
- **Log format**: `LOG_FORMAT=json` (the default for new installs) writes one JSON object per line with the request id, user, status and duration, for a log collector. Set `LOG_FORMAT=text` to read logs by eye. Requests slower than `SLOW_REQUEST_MS` are logged as warnings.
- **OpenTelemetry** (optional): set `OTEL_EXPORTER_OTLP_ENDPOINT` to the customer's OTLP/HTTP collector, for example `http://otel-collector:4318`, then `docker compose -p wms up -d`. The backend then pushes traces (each request with its SQL statements) and request metrics. Any OTLP-compatible tool works (Grafana Alloy/Tempo, Jaeger, Elastic APM, Datadog Agent); nothing is bundled. System health shows whether export is on.
- **Audit log** (System → Audit log; needs `audit.read`, which only the administrator role has by default): every change to master data, documents, users, roles, feature flags and integration settings, with each changed field's old and new value. Passwords and integration secrets are recorded as changed, never with their values. Document detail pages have a **History** button. Rows are written in the same transaction as the change, so they cannot be lost or left behind by a failed operation. The log is kept indefinitely; it grows by roughly one row per changed record.
- Installs upgraded from an earlier version keep their `.env`; add the new `LOG_FORMAT`, `SLOW_REQUEST_MS` and `OTEL_*` lines from `env.template` by hand if wanted (without them: text logs, no export).

## 11. Troubleshooting

| Symptom | What to check |
|---|---|
| The page does not open | `status.sh` to see whether every container is healthy; whether the firewall blocks the port (`firewall-cmd --list-ports`) |
| Readiness check `db_unavailable` | Cannot reach the database. Bundled database: `docker compose -p wms logs db` (common cause: under 2GB of memory). Customer database: check network, login and port |
| Readiness check `migration_pending` | Schema and code versions differ; run `docker compose -p wms run --rm --no-deps backend alembic upgrade head` |
| Backend fails to start mentioning `JWT_SECRET_KEY` | The key in `.env` was changed to the default or is too short. Restore the original value (do not change it casually: everyone must sign in again afterwards) |
| Upgrade failed and rolled back automatically | Send the screen output and `docker compose -p wms logs backend` to the developers. The system is back on the old version and can be used |
| Integrations page says "the push worker is not running" | `docker compose -p wms ps worker`, `docker compose -p wms logs --tail 100 worker`. Events created while it is stopped are not lost and are sent once it recovers |
| An external system receives no pushes | Check the status code and error in Integrations → Push log. The WMS server must be able to reach the other side (internal firewall, proxy). Integration guide: `docs/integration.md` |
| Non-Latin text shows as `???` | The customer database's collation does not support it, or a column was manually changed to a non-Unicode type; contact the developers |

## 12. Standard task durations (measured)

Measured with version 0.6.0 on the development machine (12 cores, 8GB for Docker). On customer servers the actual times are recorded in `logs/deploy.log`:

| Step | Duration |
|---|---|
| First install (bundled SQL Server, including importing about 700MB of images, creating the database and tables, initializing) | 79 s |
| First install (customer's own SQL Server) | 26 s |
| Upgrade (including backup, migration, readiness check, empty database) | 44 s |
| Rollback | 15 s |
| Automatic rollback after a failed upgrade (migration error midway) | about 30 s |

The overall SOP from receiving a server to handing over a working environment:
1. Prepare the server (install Docker).
2. Copy the package and install.
3. Run the post-install checklist.
4. Import master data.
5. Train users.

Apart from master data and training, the technical part can be done within an hour.

## 13. Security notes

- `.env` contains the database password and token signing key. It has mode 600 and only root can read it. Never commit it to a code repository or post it in a chat group.
- In production the backend refuses to start with a default or too-short `JWT_SECRET_KEY`.
- **HTTPS**: the system currently serves HTTP. When HTTPS is needed, either:
  - terminate TLS on the customer's existing load balancer / reverse proxy and forward to this service's port, or
  - add the certificate to the nginx config in the `web` container (planned for a later version).
- The API docs at `/docs` are on by default. If a security review requires turning them off, set `ENABLE_API_DOCS=false` in `.env`.
