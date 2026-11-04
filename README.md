# WMS

A warehouse management system designed for multiple tenants and multiple deployments. For background, architecture decisions and the roadmap see [docs/PLAN.md](docs/PLAN.md); for the field-level data model see [docs/data-model.md](docs/data-model.md).

Status: **Phase 8 go-live preparation is complete (waiting for the first customer pilot)**:
- Large-volume load tests and the resulting performance fixes ([docs/performance.md](docs/performance.md))
- Go-live data import (items, locations, business partners, opening stock)
- Cutover runbook, UAT cases and user guide

Earlier phases:
- Phase 7: integration framework and reports ([docs/integration.md](docs/integration.md))
- Phase 6: standardized on-prem deployment: offline install package, install/upgrade/rollback/backup scripts, industry presets ([docs/deployment.md](docs/deployment.md))
- Phase 5: extension modules, each switched on or off by a feature flag: returns, cross-docking, repacking, returnable assets
- Phase 4: outbound (order → allocate → pick → ship), shortage report, role and user management
- Phase 3: inventory (adjustments, moves, cycle counts)
- Phase 2.5: PDA scan-to-receive and putaway (offline queue, idempotent submits)
- Phase 2: inbound
- Phase 1: master data and the authentication framework

## Directory layout

```
WMS/
├── apps/
│   ├── web/       React + TypeScript + Vite frontend (web console)
│   ├── mobile/    React Native (Expo SDK 58) PDA app
│   └── backend/   FastAPI + SQLAlchemy backend
├── tools/perf/    Load-test tools: large-volume data generation, business-peak and stress tests (see docs/performance.md)
├── deploy/        On-prem deployment: packaging, install/upgrade/rollback/backup scripts, production docker-compose
├── infra/
│   └── docker/    SQL Server container for local development
├── VERSION        Release version (baked into the images at packaging time)
└── docs/
    ├── PLAN.md        Architecture and roadmap
    ├── data-model.md  Field-level data model
    ├── deployment.md  On-prem deployment runbook (SOP)
    ├── integration.md External system integration guide
    ├── performance.md Load-test report and server sizing
    ├── go-live.md     Go-live cutover runbook
    ├── uat.md         User acceptance test cases
    └── user-guide.md  User guide (training material)
```

## Development requirements

- Node.js (verified with 26.x)
- Python 3.15 (verified). On Windows the `python` command may point to the Microsoft Store stub; use the `py` launcher.
- Docker Desktop (to run the SQL Server container locally)
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- A C/C++ build toolchain: pyodbc and PyYAML have no prebuilt wheels for Python 3.15 yet, so pip builds them from source.

## First start

### 1. Start the database and create it

```powershell
cd infra/docker
docker compose up -d db
```

The container does not create the application database. Connect to `localhost,1433` (sa / `YourPassword123!`) with any SQL client and run once:

```sql
IF DB_ID('wms') IS NULL CREATE DATABASE wms
```

### 2. Backend

```powershell
cd apps/backend
py -3.15 -m venv .venv
.venv\Scripts\Activate.ps1
pip install --prefer-binary -r requirements.txt
Copy-Item .env.example .env          # edit the database connection string as needed
alembic upgrade head                 # create tables
$env:SEED_ADMIN_PASSWORD = "Admin@123"
python -m scripts.seed               # tenant/permissions/admin/units of measure; safe to rerun; --preset picks an industry preset
uvicorn app.main:app --port 8000
# In another terminal: the integration push worker (optional without external systems; events queue up and are sent once it starts)
python -m app.worker
```

API docs: `http://localhost:8000/docs`. The default admin account is `admin`, with the password set in `SEED_ADMIN_PASSWORD`.

> `--reload` is unreliable on this development machine (Windows + Python 3.15). The log shows "Reloading", but the child process that handles requests is not replaced and keeps running the old code. Restart manually after changing backend code. If port 8000 is still taken after stopping the server, kill the leftover `python.exe` (`multiprocessing.spawn`) child process.
>
> For a real PDA to reach the backend over the LAN, add `--host 0.0.0.0` and allow port 8000 through the Windows firewall.

After adding or changing models, generate a migration with `alembic revision --autogenerate -m "description"`, then run `alembic upgrade head`.

## Frontend

```powershell
cd apps/web
npm install
npm run dev
```

The dev server runs at `http://localhost:5173`. In dev mode Vite proxies `/api` to `http://localhost:8000`.

API response types (`src/api/types.ts`) are aliases of types generated from the backend's OpenAPI schema. After changing a backend schema, regenerate them and commit both files (CI fails if they are stale):

```powershell
cd apps/backend; python -m scripts.export_openapi   # writes apps/web/openapi.json
cd ../web; npm run gen:api                           # writes src/api/schema.d.ts
```

## Tests and checks

CI (`.github/workflows/ci.yml`) runs all of these on every push and pull request.

```powershell
cd apps/backend
pip install --prefer-binary -r requirements-dev.txt
python -m playwright install chromium   # once, for the browser tests
ruff check .                            # lint
pytest --ignore=tests/e2e               # API and service tests
pytest                                  # also browser tests; build the web app first (cd apps/web; npm run build)
```

- Tests run against a separate database: the name from `DATABASE_URL` with `_test` appended (override with `TEST_DATABASE_URL`). It is created, migrated and seeded automatically, and the development database is never touched.
- Tests share that database and don't clean up after themselves. Each test creates its own master data with unique codes; follow the same pattern (see `tests/helpers.py`).
- The browser tests sign in, open every page and fail on any error in the browser console. To also catch React and antd warnings, point them at a development build: `npx vite build --mode development --outDir <dir>`, then set `WEB_DIST=<dir>`.
- Web: `npm run typecheck`; mobile: `npm run typecheck`.

## Mobile (PDA)

```powershell
cd apps/mobile
npm install
npm run web          # preview in the browser: http://localhost:19006 (the backend's CORS allows this origin)
npm run typecheck    # type check
npx expo-doctor      # dependency/config check
```

Install dependencies with `npx expo install <package>`, which picks versions compatible with SDK 58. Don't use `npm install <package>` directly.

**Building for devices** (not yet verified on this machine; needs extra setup):
- **Local build**: install Android Studio / Android SDK + JDK, run `npx expo prebuild`, then `npx expo run:android --variant release`. No Expo account is needed, which suits isolated networks.
- **Cloud build**: `npx eas-cli@latest build -p android`. Needs an Expo account and internet access.
- `app.json` enables Android `usesCleartextTraffic`. On-site backends usually use plain http, which Android 9+ blocks by default.

**PDA features**:
- Receive, put away and move.
- Count: cycle counts are started in the web console. On the PDA, choose a count, then scan locations and items. The quantity field is not prefilled with the book quantity.
- Pick: guided in bin order (scan bin → scan item → confirm quantity). Short picks are allowed, and a line can be skipped and picked later. The pick list is posted once every line is confirmed.

**Scanner setup**: set the PDA to keyboard wedge mode (Keystroke/DataWedge keyboard output) with the barcode suffix set to **Enter**. The app's scan field keeps focus and hides the soft keyboard by default; tap "Keyboard" to type by hand.

**Offline use and resubmits**:
- After sign-in, master data (items, barcodes, unit conversions, stockable locations) is downloaded to the device. Barcodes are resolved locally, so scanning works offline.
- Purchase orders and location stock are fetched fresh and cached while online. Offline, the cache is used and the app warns that the data may be out of date.
- Submits go to a local queue and are sent to the server in order:
  - **Offline or server error**: kept and retried every 20 seconds.
  - **Session expired**: paused until the user signs in again.
  - **Rejected under business rules** (over-receipt, insufficient stock, ...): moved to the "Failed" list for manual handling. A draft already created on the server is cancelled automatically.
- Every submit carries a unique `client_request_id`. If the same ID is submitted again (for example, the request reached the server but the response was lost), the server returns the existing document instead of posting twice.
- Count entries have "set" semantics (resubmitting gives the same result), so they need no request ID.

**Known limitations**:
- On native, PDA master data is stored as a file (expo-file-system). This is verified in the browser preview; file I/O on a real device still needs testing once an Android device is available.
- The submit queue belongs to the device, not the user. If user A submits offline and user B later signs in on the same device, A's records are submitted as B.
- Sign-in tokens expire after 60 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`), so users must sign in again during a full shift. A refresh token can be added later.

## Deploying to a customer site

For packaging, installing, upgrading, rolling back and backing up, see [docs/deployment.md](docs/deployment.md). In short:

```bash
bash deploy/build-release.sh --with-db          # build machine: produces deploy/dist/wms-<VERSION>.tar.gz
bash install.sh --dir /opt/wms --preset standard  # customer server: run after extracting the package
```

- In production (`APP_ENV=production`) the backend requires a random `JWT_SECRET_KEY` and refuses to start with the default. The install script generates one.
- `GET /api/v1/health` returns the version.
- `GET /api/v1/health/ready` checks the database connection and that the schema version matches the code.

## Implemented APIs

**Authentication and access**
- `POST /api/v1/auth/login`: sign in and get a JWT
- `GET /api/v1/auth/me`: current user and permissions (the frontend uses it to show menus and buttons)
- `/api/v1/users` (including `PUT /{id}` to change profile/roles/active and `POST /{id}/reset-password`), `/api/v1/roles`, `GET /api/v1/permissions`: user, role and permission management

**Master data**
- `GET/POST/PUT/DELETE /api/v1/business-partners`: business partners (customers/suppliers)
- `GET/POST/PUT/DELETE /api/v1/items`: items
- `GET/POST/PUT/DELETE /api/v1/locations`: locations (self-referencing tree)
- `GET /api/v1/uoms`: units of measure
- `/api/v1/reason-codes`: reason codes such as adjustment reasons; list, create, update

**Inbound**
- `/api/v1/purchase-orders`: purchase orders; list, create, detail, edit (draft), `/{id}/confirm`, `/{id}/cancel`, `/{id}/close`
- `GET /api/v1/purchase-orders?doc_no=`: exact lookup by document number (used when the PDA scans a PO number)
- `/api/v1/grns`: goods receipts; list (filter by `po_id`), create, detail, `/{id}/post`, `/{id}/cancel`
- `/api/v1/putaways`: putaways; list (filter by `grn_id`), create, detail, `/{id}/post`, `/{id}/cancel`

**Inventory**
- `/api/v1/moves`: moves; same endpoints as putaways (both are generated by one factory in `api/v1/transfers.py`)
- `/api/v1/adjustments`: stock adjustments; list, create, detail, `/{id}/post` (approve and post), `/{id}/cancel`
- `/api/v1/cycle-counts`: cycle counts; list, start, detail, `/{id}/counts` (enter counts, safe to resubmit), `/{id}/recount`, `/{id}/post`, `/{id}/cancel`
- `GET /api/v1/stock/balances`, `GET /api/v1/stock/ledger`: stock balances and ledger

**Outbound**
- `/api/v1/sales-orders`: sales orders; list, create, detail (with fulfilment progress), edit (draft), `/{id}/confirm`, `/{id}/allocate` (creates pick lists), `/{id}/cancel`, `/{id}/close`
  - `GET /sales-orders/shortages`: shortage report
  - Allocation accepts `source_location_id` for cross-docking; requires `CROSS_DOCK` to be enabled.
- `/api/v1/picks`: pick lists; list, detail, `/{id}/lines/{line_id}/confirm` (enter the picked quantity, safe to resubmit), `/{id}/confirm-all`, `/{id}/post`, `/{id}/cancel`
- `/api/v1/shipments`: shipments; create from an order (picked but unshipped goods are filled in), detail, `/{id}/info` (loading details), `/{id}/post`, `/{id}/cancel`

**Extension modules** (controlled by feature flags)
- `/api/v1/returns-in`, `/api/v1/returns-out`, `/api/v1/repacks`: customer returns, returns to supplier and repacks; list, create, detail, `/{id}/post`, `/{id}/cancel`
- `/api/v1/returnable-assets`: returnable assets; `/types`, `/transactions` (lend/return records), `/balances` (outstanding balances)

**Reports, integration and system**
- `GET /api/v1/reports/dashboard|turnover|picker-kpi|expiry|partner-ledger`: dashboard and reports (permission `report.read`)
- `/api/v1/integration`: integrations; `/connectors` (create/update/delete, `/test`, `/rotate-secret`), `/jobs` (push log, `/{id}/retry`), `/event-types`, `/summary`
- `GET /api/v1/mobile/master-data`: PDA master data download (permission `mobile.sync`)
- `GET /api/v1/features`, `PUT /api/v1/features/{code}`: feature flags (changes require `system.settings`)

**Idempotent submits**: creating a GRN or putaway accepts a `client_request_id` (8–64 characters).

For status transitions and concurrency rules see section 8 of [docs/data-model.md](docs/data-model.md).

Not yet implemented:
- Maintenance screens for units of measure and unit conversions (`item_uom_conversion`)
- Outbound checking/packing, wave picking and replenishment suggestions
- Return handling on the PDA

**Extension modules** (returns, cross-docking, repacking, returnable assets) are off by default. Enable them per tenant under "System → Feature flags".

**Permissions**: permissions are not stored in the sign-in token; each request reads them from the database. Changes to role permissions or deactivated accounts under "System" therefore **take effect immediately**, without the affected user signing in again.
- The system role ADMIN always has every permission and cannot be edited or deleted.
- Administrators cannot deactivate themselves or remove their own user-management permission.

**Example split of duties** (create roles under "System → Roles"):
- **Clerks**: data-entry permissions such as `adjustment.create`, `cycle_count.count` and `pick.confirm`.
- **Supervisors**: additionally `adjustment.post`, `cycle_count.post` and `pick.post` (approve and post, request recounts), plus `cycle_count.view_expected` (see book quantities while counting).
- Users without `view_expected` count blind.

## SQL Server dialect notes

Pitfalls already hit during development; keep them in mind when writing new models or queries:
- **Always use `Unicode(n)` (NVARCHAR) for text columns, never `String(n)`.** On SQL Server, `String` creates VARCHAR, and with the default collation non-Latin text (such as Chinese) is stored as `???`.
- For boolean filters, use `== false()`, not `.is_(False)`. The latter generates `IS 0`, which SQL Server does not support.
- Paging with `.offset()` requires `.order_by()`.
- Import new models in `app/models/__init__.py`, or foreign keys cannot find the referenced table at runtime.
- For row locks, use `.with_hint(Model, "WITH (UPDLOCK, ROWLOCK)", "mssql")` with `populate_existing=True` so you get the latest values after locking (see `services/document_common.py`).
- `SessionLocal` has autoflush off. To query after a change in the same transaction, call `db.flush()` first.

## Audit log and request context notes

- Changes are audited automatically by a flush hook (`app/models/audit.py`); services need no code for it. A new model is audited only once it is listed in `_AUDITED` there; add new secret columns to `_SECRETS`.
- The hook cannot see bulk `update()`/`delete()` statements. A service that uses one on an audited table must call `record_change()` itself, like role permissions and user roles do.
- `current_context()` (`app/core/request_context.py`) gives the request id and signed-in user anywhere in a request; outside a request (worker, scripts) it is empty and the audit log records "System".

## Live updates notes

- Pages refresh by themselves when anyone changes data: the backend streams change events (`GET /api/v1/events/stream`, server-sent events) read from the audit log (`app/services/live_service.py`), and `src/api/live.ts` refetches the affected React Query keys. Events carry only record type, id and action, never values.
- So a change shows up live only if it is audited (see above). New query keys: add them to the maps in `src/api/live.ts`.
- A form that copies fetched data into its fields must do it once per source document (see the `filledFrom` ref in `OrderForm.tsx`), or a live refetch wipes what the user is typing.
- One stream per browser: tabs elect a leader through a localStorage lease and share events over a `BroadcastChannel`.

## List page notes

- Document lists take the shared filters of `app/api/filters.py` (status, keyword, created-date range in the business time zone, paging); a new document list endpoint should use `Depends(document_filters)` too.
- Saved views and visible columns are per-user preferences on the server (`/me/preferences/{key}`, `src/api/preferences.ts`), keyed `list:<path>`. Never save one before it has loaded (`loaded`): a save built from the defaults would overwrite the user's stored settings.
- Batch actions (`batchActions` on `DocumentListPage`) call the normal per-document endpoints one at a time; give each action exactly the statuses its endpoint accepts (see the services' `require_status`).

## Frontend notes

- Use `showError` (`src/api/errors.ts`) for React Query `onError`, not `(e) => message.error(...)`. React Query awaits the returned antd message until it closes, so after an error the button spins for about 3 more seconds and ignores clicks.
- Add `onKeyDown={preventEnterSubmit}` to document entry forms. Scanners send Enter after every scan, and Enter must not submit the document.
- In dev mode antd forms occasionally log "There may be circular references". This is a false positive from rc-field-form comparing field metadata and is unrelated to application code.
