# WMS Development Plan

> Reference: `C:\Ninso\94weijun\Ninso` (an ASP.NET MVC WMS for FMCG/distributor warehouses)
> Target stack: React (TypeScript) + Python (FastAPI) + SQL Server
> Core requirement: smooth, usable business processes, while being **multi-tenant and configurable** so the system can be applied to different companies without code changes

---

## 1. Design principles

1. **Follow Ninso's processes, but use industry-neutral names.**
   - Ninso's module names follow its own customers' terminology (e.g. `Outlet`, `Tool`, `PMA`).
   - The new system keeps the process semantics but models them with generic vocabulary (see section 4), so a new customer needs only configuration/translation, not schema changes.
2. **Configuration-driven, not code branches.** Differences between companies are handled with **tenant configuration tables + feature flags + dynamic forms**, not piles of if-else or code branches. Examples: numbering rules, whether cross-docking/repacking is enabled, batch/expiry management, approval levels, document fields.
3. **API-first.** Every business action is a backend REST/RPC API. The web console (React), PDA/mobile scanning apps and third-party ERP integrations all use the same API.
4. **Single source of truth for stock.**
   - Every stock movement (receiving, putaway, picking, adjustment, counting, moves) must be written to one `stock_ledger` table.
   - Current stock is an aggregate of the ledger; stock fields are never changed directly in several places.
5. **Foundation first, then muscle.** Phase 1 makes master data, the stock ledger model and the permission/multi-tenant framework solid. Later modules add CRUD + process state machines on that foundation, so each new module costs less.

---

## 2. Business modules distilled from Ninso

From a scan of `Controllers/`, `DataModels/` and `Views/`, Ninso's business scope is roughly:

| Domain | Ninso features | Notes |
|---|---|---|
| Master data | Item, Supplier, Outlet, UOM, PackingSpec, BinNum/BinType/Rack, Category, Division/Department | SKUs, suppliers, customers (outlet = store/distribution point), location structure |
| Purchasing/inbound | PO, GRN/GR, StockIn, POShort, POReceivingStatus | Purchase order → receipt → short/over handling |
| Putaway/locations | InBin, MoveLocation, CombineLocation, BinNumLock, RackingUsage | Putaway after receipt, moves, location locks, utilization |
| Cross-docking | CrossDock, CrossDockSub, CrossDockReport | Direct flow-through, bypassing regular storage |
| Repacking | Repack, RepackGR, RepackLoading, RepackItemSub | Split/recombine original packs and put back into stock |
| Inventory management | SkuLedger, Adjustment, OpeningStock, ClosingStock | Stock ledger, adjustments, opening/closing stock |
| Counting | CycleCount, Stocktake, Audit, AuditVariance | Cycle counts, full counts, variance review |
| Replenishment | Replenish, ReplenishStatus, DailyReplenish | Pick-face/forward replenishment |
| Sales/outbound | OutletOrder, OrderList, OrderShortage, SKUOOS | Customer orders, shortage handling |
| Allocation/picking | ManualAllocation, LoadingManualAllocation, Picking, PickList, PickerIndiKPI/GroupKPI | Location allocation → picking → picker performance |
| Loading/shipping | NormalLoading, PickingCD, PrintPickingList | Loading lists, printing |
| Returns | ReturnNote, ReturnSupplier, GoodReturn, SupplierReturnLedger | Customer returns, returns to supplier |
| Tools/returnable assets | Tool, ToolOneMany, ToolManyOne, ToolReceive/Return | Lending/returning pallets, baskets, carts etc. (generalizable as "returnable asset management") |
| Reports/dashboard | DashboardSummary, TurnOverReport, SupplierLedger, OutletLedger | Dashboard, turnover, statements |
| System/integration | SystemConfiguration, User/Login, *ApiLog (Po/Grn/Do/Item/Customer) | User permissions, two-way sync logs with an external ERP |

**Key observations**:
- **Integration**: Ninso syncs with an external ERP asynchronously through many `XxxGetApiLog` / `XxxPostApiLog` tables. The new system should make "integration sync" a separate module instead of one implementation per document type.
- **Partners**: `Outlet` is essentially a "ship-to" party and `Supplier` a "ship-from" party. They can be merged into one `BusinessPartner` table with role flags, reducing duplicate modelling.
- **Documents**: `PO/GRN/SO/DO/Adjustment/Transfer` are all "header + lines + state machine". One document framework can carry them all, differing only in document type and status transition rules.

---

## 3. Multi-tenant / configurable design (key)

This is the core mechanism for applying the system to different companies.

### 3.1 Tenant isolation model (adjusted for "target customers = large enterprises + on-prem deployment allowed")

> Confirmed: there is no specific customer yet, but the expected customers are **sizeable enterprises**, and **on-prem deployment is allowed**. Large enterprises usually have their own IT and data security requirements and prefer "one isolated environment per company" over sharing a database with other companies. The isolation strategy was therefore reprioritized:

- **Primary model: single tenant per deployment.**
  - Each customer gets an isolated deployment (its own database instance and application services), in the customer's own data center/private cloud or in an isolated environment we host.
  - Customers are physically isolated, with none of the security risk of "a shared database separated by filters". This fits large enterprises' security review practices best.
- **Keep the `tenant_id` column anyway** (almost free, but keeps flexibility):
  - Internal demo/test environments can run several fake tenants.
  - If small customers later want a low-cost shared SaaS model, no code changes are needed: switch isolation from "separate deployment" to "row-level isolation" (SQL Server Row-Level Security).
  - Even in a single-tenant deployment, `tenant_id` naturally maps to "multiple warehouses/legal entities", which is common at large enterprises (one system for several subsidiaries or warehouses), so it is not wasted.
- **"Applying the system to different companies" relies on section 3.4's "deployment presets + configuration", not on runtime multi-tenancy.** After a new customer signs, a standardized script/process brings up an isolated environment with default configuration, instead of adding the customer to an existing shared instance.

### 3.1.1 Impact of on-prem deployment on the architecture

> Confirmed: customer networks are **usually internal and not internet-facing** (deployed on the customer's internal network, not exposed publicly). Details (internet access, Kubernetes, who provides the SQL Server instance) will be planned with a specific customer. For now the conservative assumption is "internal network first, works offline", with no public internet or cloud services assumed.

- **Packaging**: Docker Compose (default) bundles "frontend + backend + queue + reverse proxy" images. SQL Server is either the customer's existing instance or a bundled container. For customers with Kubernetes, a Helm chart can be provided additionally.
- **Offline/internal network**: assume an isolated internal network with no or weak internet access.
  - Install packages must support offline image import (`docker save/load`).
  - At runtime nothing depends on external services that need internet access (cloud logging/monitoring/third-party APIs). Such capabilities are optional and off by default.
- **Upgrades**: an upgrade = new images + Alembic database migrations. Support both "the customer upgrades by following the docs" and "we upgrade remotely/on site". Upgrades must be reversible.
- **License/compliance**: **skipped for now**; no license files or usage control. Only avoid hard-coding things like "must verify online", leaving room to add licensing later.
- **Enterprise identity (AD/LDAP/SSO)**: **skipped for now**; the built-in account + role system (see 3.3 RBAC) is used.
  - The user model must not assume "always a local password": the password field can be empty, and the sign-in method is an extensible provider field. Integrations can then be added later without schema changes.
  - Protocol choice and integration development are out of scope for this phase.

### 3.2 Configuration layers
| Layer | Content | Storage |
|---|---|---|
| Tenant basics | Company info, logo, time zone, default language, unit system | `tenant_settings` table |
| Feature flags | Whether to enable cross-docking / repacking / batch management / expiry management / serial numbers / returnable assets / multi-warehouse zones | `tenant_feature_flags` table; the backend reads it per tenant to decide which menus and validation rules apply |
| Numbering rules | Prefix and length of PO/GRN/SO/DO numbers, whether to reset by year/month | `doc_number_rule` table, templates like `{PREFIX}-{YYYYMM}-{SEQ:6}` |
| Business rule parameters | Picking strategy (FIFO/FEFO/LIFO), whether over-shipping is allowed, count frequency, safety stock thresholds | `tenant_business_rules` (JSON column for extensible parameters, core fields structured) |
| Approval flow | Whether purchasing/adjustments/returns need approval, approval levels | `approval_workflow` + `approval_step`, driven by a simple state machine engine |
| Custom fields | Extra fields some companies need on items/customers/documents (e.g. shelf life days, cold-chain temperature zone) | EAV-style `custom_field_definition` + `custom_field_value`, avoiding per-customer schema changes |
| UI/form customization | Visible list columns, required fields, dropdown options | The frontend renders from a "form schema" (JSON) instead of hard-coded forms |

### 3.3 Roles and permissions
- RBAC: `role` → `permission`, at module + action granularity, e.g. `grn.create`, `picking.confirm`.
- Tenants can define their own roles (some customers want a "pick supervisor" role, others do not). Permission codes are fixed system-wide, so the checks in code do not vary by tenant.

### 3.4 "Industry preset" mechanism
To get a new company running quickly, use **deployment presets (industry presets)**:
- When a new customer is first set up, choose a preset such as "FMCG distribution", "3PL" or "cold-chain warehouse".
- The preset writes a default set of feature flags, numbering rules, role permissions and base master data (UOMs, adjustment reason codes, etc.).
- Implementation staff then fine-tune it instead of configuring from scratch.

---

## 4. Technical architecture

### 4.1 Frontend: React
- **React 19 + TypeScript + Vite** (React Router 7, Ant Design 6; API types generated from the backend OpenAPI schema)
- **UI library**: **Ant Design** recommended (mature for table/form-heavy consoles, built-in i18n), with custom theme variables for per-tenant colors and logos.
- **State management**:
  - **TanStack Query** for server data, caching and retries.
  - **Zustand or Redux Toolkit** for a little global UI state, such as the current tenant and user.
- **Routing**: React Router, with menus generated by permission. The menus themselves are driven by backend data, not hard-coded.
- **Forms**: React Hook Form + Zod validation. Form fields can be generated from a backend schema (together with the custom fields in 3.2).
- **i18n**: i18next (English at minimum, extensible).
- **Scanning/hardware**:
  - In the browser, "keyboard wedge" scanners come first (USB/BT HID mode, input arrives as text in a field).
  - Leave an interface for WebUSB/WebSerial or native PDA (Android + browser/WebView) scanning SDKs.
  - Labels are printed from backend-generated PDF/ZPL; the frontend triggers print jobs.
- **Build output**: route-level code splitting per module (lazy load) to reduce initial load.

### 4.2 Mobile / PDA (confirmed as needed)

Floor work in large warehouses (receiving, putaway, picking, counting, moves) depends on handheld scanners. This is a separate development track from the web console but **uses the same backend API**.

- **Technology: React Native.**
  - It shares the TypeScript skill set with the web; some business logic and type definitions can be reused via `packages/shared-types`.
  - The confirmed scanning approach is keyboard wedge (see below), so no native hardware vendor SDK and no native Android shell are needed. React Native covers every requirement.
- **Scanning: keyboard wedge mode (HID/DataWedge).**
  - The scanner or rugged device sends each scan as typed text, and the app receives it in a focused hidden input.
  - This gives the best compatibility, is not tied to a hardware brand and needs no vendor SDK, so development and maintenance cost the least.
  - Native scanning SDKs (continuous scanning, vibration feedback and other enhancements) are out of scope unless a customer explicitly needs them and the hardware is chosen; that would be evaluated separately.
- **Offline-first design**: warehouse networks often have dead zones, so the app must:
  - Queue unsent scan actions locally (local SQLite/MMKV) and retry automatically when the network returns.
  - Cache key master data (SKUs, locations) locally with periodic sync, so scans do not wait on the API.
- **Scope (high-frequency floor actions on mobile first)**: receiving, putaway, picking confirmation, count scanning, moves, and returnable asset lend/return scans. Reports and configuration stay in the web console.
- **Timing**: mobile does not need to start with the web. Start each mobile module right after the matching web module's API (receiving/inventory/outbound) stabilizes, rather than building both in parallel from the start, to avoid API rework.

### 4.3 Backend: Python
- **FastAPI** (async, automatic OpenAPI docs, Pydantic validation; a natural fit for one API serving the React frontend and the PDA)
- **ORM**: **SQLAlchemy 2.0 + Alembic** (migrations)
- **Validation/serialization**: Pydantic v2 schemas, with separate `Create / Update / Read` DTOs
- **Layered architecture**:
  ```
  api/        routes (validate parameters, call a service, return)
  services/   business logic (transaction boundaries, state machines, rule engine)
  repositories/ data access (SQLAlchemy query wrappers)
  models/     ORM models
  schemas/    Pydantic DTOs
  core/       tenant middleware, permission middleware, configuration, error handling
  tasks/      async tasks (Celery/RQ)
  ```
- **Authentication**: JWT (access + refresh), with tenant info and permission codes in the token claims. SSO/AD/LDAP can be added later (common for large customers).
- **Async task queue**: **Celery + Redis** (or RQ, depending on team familiarity). Used for:
  - Async sync with external ERPs. This follows Ninso's ApiLog pattern, but with unified `integration_job` + `integration_log` tables instead of one log table per document.
  - Bulk Excel import/export, report generation, label/document print queues.
- **Multi-tenant middleware**: each request parses the token, gets `tenant_id` and injects it into the database session context. Every repository query then filters by tenant automatically, e.g. via SQLAlchemy `with_loader_criteria` or custom session events.
- **API style**: mainly REST (resources: `/api/v1/purchase-orders`). Strongly action-like operations such as "confirm pick" or "scan" use explicit action endpoints (`/picking-tasks/{id}/confirm`) instead of overloading PATCH for status transitions.

### 4.4 Database: SQL Server
- Use SQL Server **Row-Level Security (RLS)** as a backstop for tenant isolation (even if the application forgets a `tenant_id` filter, the database blocks it).
- Every table has the same audit columns: `id (uniqueidentifier/bigint)`, `tenant_id`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted` (soft delete).
- Document tables share the "header + lines" structure (see section 5).
- **Stock concurrency**: high-concurrency operations such as picking, putaway and counting use **optimistic locking (rowversion column)** or row locks to prevent overselling.
- **Indexes**: the SKU + location + batch composite index is the hot spot; design covering indexes up front.
- **Historical data**: partition big tables (stock_ledger, pick_task) by time or archive them to history tables regularly, so the system does not slow down over time.

### 4.5 Integration layer (no concrete need yet: "reserve the framework, implement later")
- **Connectors**: a unified `integration_connector` configuration; each tenant can configure several external systems (ERP/finance/TMS).
- **Jobs and logs**: unified `integration_job` (tasks) + `integration_log` (request/response/status of every call). This replaces Ninso's one ApiLog table per document.
- **Events**: outbound webhooks/callbacks, so customers' systems can subscribe to events such as "GRN completed" or "DO shipped".
- **Priority**: there is no specific customer and no confirmed external system yet.
  - This phase only designs the shell of this "pluggable integration framework": the tables plus the reserved job/log mechanism.
  - Specific connectors (e.g. SAP or other ERPs) are **out of initial scope**. They will be built once a customer confirms the system to integrate with, to avoid speculative work.
  - Large enterprises almost always have an ERP already, so this will be needed sooner or later. The framework is reserved, but filling it in is not urgent.

### 4.6 Deployment and infrastructure
- **Default form: Docker Compose packages, one isolated environment per customer** (see 3.1.1).
  - It can run in the customer's data center/private cloud or be hosted by us.
  - Customers with Kubernetes can additionally get a Helm chart; the architecture is not tied to one deployment method.
- **Offline install packages** (image export/import) for large enterprises' isolated internal networks without internet access.
- **CI/CD**: lint + unit tests + integration tests + automatic migrations + image build → a "deliverable install package" (not just a deployment to our own cloud).
- **Environments**: dev / staging / a separate production per customer.
- **Upgrade and rollback**: versioned Alembic migrations + image tags, with a self-service upgrade manual and rollback plan for customers.
- **Logging/monitoring**:
  - Structured logs that include `tenant_id`, for troubleshooting per tenant and per deployment.
  - APM (e.g. OpenTelemetry). In on-prem deployments, sending data out is off by default and logs stay on local disk.
  - Stock anomaly alerts.

---

## 5. Data model design principles (generic)

| Generic table | Replaces in Ninso | Notes |
|---|---|---|
| `business_partner` (+ `type`: customer/supplier) | `Outlet`, `Supplier` | Customers and suppliers merged, distinguished by a role field, avoiding duplicate columns |
| `location` (warehouse > zone > aisle > rack > bin; self-referencing tree or path table) | `BinNum`, `Rack`, `BinType`, `AreaView` | Generic location structure with any number of levels |
| `item` + `item_attribute` (batch/expiry/serial switches) | `Item`, `BarcodeItem`, `PackingSpec` | SKU master data; tenant feature flags decide whether batch/expiry validation applies |
| `document_header` + `document_line` (`doc_type`: PO/GRN/SO/DO/ADJUST/TRANSFER/RETURN) | Separate tables for PO/GRN/OutletOrder/NormalLoading/Adjustment/ReturnNote etc. | One document framework; type-specific fields go in extension tables or JSON columns, reducing duplicated header/line tables |
| `stock_ledger` (the only stock ledger) | `SkuLedger`, `ClosingStock`, `OpeningStock` | The only entry point for stock changes; current stock = an aggregate view or the materialized `stock_balance` table |
| `task` (picking/replenishment/counting/move tasks in one abstraction, distinguished by `task_type`) | `PickList`, `Replenish`, `CycleCount`, `MoveLocation` | In-warehouse execution tasks share assignment/status/operator fields |
| `returnable_asset` + `returnable_asset_transaction` | `Tool`, `ToolOneMany`, `ToolManyOne` | Generalized as "returnable assets" (pallets, roll cages, trays); not every customer needs it, so it is behind a feature flag |
| `kpi_snapshot` / reports via read-only views or an OLAP layer | `PickerIndiKPI`, `TurnOverReport` | Avoid extra business tables for reports; use views/scheduled summary tables |

> Trade-off: the unified `document_header/line` framework reduces duplicate modelling but loses some strongly typed per-table constraints. For the core high-frequency documents (PO, GRN, SO, DO, stock adjustment), use the unified framework plus typed "extension detail tables" (1:1, holding only that document type's own fields), balancing flexibility and query performance.

---

## 6. Core business processes (state machine outline)

Aligned with Ninso's processes, but described in generic terms, so "customer A's process" vs "customer B's process" can later be compared as configuration differences:

1. **Purchasing/inbound**: `create PO → approval (configurable) → GRN (full/partial/short/over) → QC (configurable) → putaway → inbound complete`
2. **Cross-docking** (optional module): `mark cross-dock SKUs on the PO/GRN → skip regular storage → create outbound tasks directly`
3. **In-warehouse movement**: `move / combine locations / replenish (from bulk to pick face)`
4. **Counting**: `create cycle count tasks → counters scan → differences arise → review → stock adjustment posted`
5. **Sales/outbound**: `receive sales order (API/manual) → shortage check → location allocation (auto/manual) → create pick tasks → confirm picks → check/pack (configurable) → load → DO complete → stock deducted`
6. **Returns**: `customer return → QC sorting (usable/damaged) → restock or write off → return to supplier (reverse flow)`
7. **Returnable assets** (optional module): `record lending → reconcile → record return → overdue reminders`
8. **Integration**: `pull orders/materials from the external ERP → process locally → push results back to the ERP`; every step is written to `integration_log` for tracing and retries

Each state machine is driven by a `workflow_definition`. Tenants can override the default flow (e.g. customer A requires QC on GRNs and customer B does not) instead of it being hard-coded in branches.

---

## 7. Non-functional requirements

- **Permissions and audit**: every write leaves an audit log (who changed what, when, and the previous value) to meet customers' compliance audits.
- **Multiple languages**: UI text and printed document templates support multiple languages.
- **Performance**: load-test concurrent writes to the stock ledger at receiving/picking peaks. Once a target daily volume per warehouse is set, derive the database index/partition strategy from it.
- **Offline/weak network**: warehouse Wi-Fi often has dead zones, so the PDA/scanning side must cache briefly offline and resubmit.
- **Observability**: key business metrics (order processing time, pick accuracy, stock accuracy) should be generated automatically from logs/data, without building extra reporting infrastructure.
- **Enterprise identity (AD/LDAP/SSO), license/usage control**: confirmed as **skipped** for the current phase. The data model only keeps room to extend (see 3.1.1); no implementation.

---

## 8. Suggested project structure (monorepo)

```
WMS/
├── apps/
│   ├── web/              # React frontend
│   └── backend/           # FastAPI backend
├── packages/
│   ├── shared-types/      # Types shared by frontend and backend (generated from OpenAPI)
│   └── ui-kit/             # Common UI components/theme
├── infra/
│   ├── docker/
│   ├── k8s/ (optional)
│   └── migrations/        # Alembic
├── docs/
│   ├── PLAN.md            # This file
│   ├── data-model.md
│   └── api-spec/ (OpenAPI export)
└── scripts/                # Tenant initialization, preset import, etc.
```

---

## 9. Roadmap

There is no signed customer yet, but the targets are clear: large enterprises, on-prem deployment allowed, and a mobile app needed. The roadmap therefore:
- Makes the reusable foundation and deployment capability solid first, then builds out business modules.
- Staggers web and mobile work on the same module: mobile starts right after the matching web module's API stabilizes.

| Phase | Goal | Output |
|---|---|---|
| **Phase 0 — Requirements and modelling** (1–2 weeks) | Outline the generic data model and draft API; clarify enterprise non-functional requirements (AD/SSO expectations, typical on-prem IT environment assumptions, whether licensing is needed) | Data model, tenant/deployment configuration checklist, OpenAPI draft |
| **Phase 1 — Foundation** (3–4 weeks) ✅ Done (offline install package completed in Phase 6) | Authentication and permissions (with AD/SSO extension points), master data (business_partner/item/location), document framework skeleton, deployment packaging (Docker Compose) proven by one "environment from scratch" run | Sign-in, master data creation, a minimal runnable environment installable offline |
| **Phase 2 — Inbound web** (2–3 weeks) ✅ Done | PO → GRN → putaway end to end | Inbound loop usable |
| **Phase 2.5 — Mobile receiving/putaway** (1–2 weeks, right after Phase 2) ✅ Done (Expo SDK 58; verified in the browser, device builds pending an Android environment) | React Native scan-to-receive and putaway working; validate hardware scanner compatibility and the offline queue design | Mobile technical approach settled, usable as the template for later modules |
| **Phase 3 — Inventory web + mobile** (2–3 weeks) ✅ Done | Stock ledger, adjustments, moves, cycle counts; mobile covers count and move scanning | Stock accuracy verifiable; floor counting without paper |
| **Phase 4 — Outbound web + mobile** (3–4 weeks) ✅ Done (checking/packing, wave picking and replenishment suggestions deferred) | Order → allocate → pick → load → DO; mobile covers pick confirmation | Outbound loop usable, with picker KPIs |
| **Phase 5 — Extension modules** (as needed) ✅ Done (return handling on the PDA deferred) | Cross-docking / repacking / returns / returnable assets, switched by feature flags | Optional modules live |
| **Phase 6 — Standardized on-prem deployment** (2 weeks, can be refined alongside Phases 2–4) ✅ Done (licensing skipped as agreed; HTTPS and Helm chart when a customer needs them; see docs/deployment.md) | Make the "one environment per customer" delivery process work: install docs, offline image package, upgrade/rollback scripts, (optional) licensing | A standard operating procedure (SOP) from contract to working environment, with measurable duration |
| **Phase 7 — Integration framework and reports** (framework first, connectors later) ✅ Done (webhook push + jobs/logs + dashboard and 4 reports; dedicated ERP connectors and API keys for external systems when a customer needs them) | Integration job/log tables, webhook skeleton, dashboard; specific ERP connectors once a customer confirms them | Integration extension points ready, dashboard usable |
| **Phase 8 — UAT / first customer pilot** (parts not needing a customer ✅ done: load tests and performance fixes, data import, go-live/UAT/training docs; on-site load test, training and phased go-live after signing) | Load testing, training, phased go-live in the first on-prem environment | Production use, feeding back into the Phase 6 SOP |

---

## 10. Open questions

### Confirmed (2026-10-24)
1. **Customers**: no signed customer yet, but the targets are **sizeable enterprises**.
   - The architecture follows enterprise requirements: isolated deployments, strong permission auditing, room for enterprise identity integration.
   - Load-test targets will be derived from real SKU counts and daily order volumes after signing.
2. **Ninso data**: **no** compatibility with or migration of Ninso's historical data is needed, so ETL migration was removed from the roadmap.
3. **Mobile/PDA**: **needed**. Section 4.2 gives the approach (React Native first; native only if a hardware SDK is required), developed alongside Phases 2.5/3/4.
4. **External systems**: **no** existing ERP/finance system has to be connected in the first phase, so the integration module was downgraded to "framework first, connectors later" (see 4.5 and Phase 7).
5. **On-prem deployment**: **allowed**. Isolation moved from "shared-database multi-tenancy" to "primarily single-tenant isolated deployments" (see 3.1). Deployment packaging, offline install and upgrades became formal Phase 6 deliverables.

### Confirmed (2026-10-24, second round)
6. **Mobile scanning**: **keyboard wedge scanning (HID/DataWedge)**, with no hardware vendor SDK. Section 4.2 is updated, and React Native is the settled choice with no fallback option.
7. **On-prem network assumptions**: customer environments are **usually internal and not internet-facing**.
   - Details (internet access, Kubernetes capability, who provides the SQL Server instance) will be planned with a specific customer.
   - Section 3.1.1 adopts the conservative assumption: "internal network first, works offline, no online verification".
8. **License mechanism**: **skipped**; no investment in this phase.
9. **Enterprise identity (AD/LDAP/SSO)**: **skipped**. The built-in account system is used, with only extension fields reserved in the user model.

### Still to settle before formal kick-off
1. **Industry and size of the first customer.**
   - As soon as there is a prospect, run another Phase 0 site survey: actual process differences, SKU/order volumes, current systems, and the real constraints of the customer's network and servers.
   - Use the real data to calibrate the conservative assumptions in this plan.
   - This is the only open question that would materially change priorities. The rest of the technology choices are essentially settled, and Phase 1 foundation work can start.

---

> This document contains no code; it sets the architecture direction and module scope. Before writing code, review and adjust it with the results of Phase 0.
