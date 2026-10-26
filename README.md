# WMS

多租户/多部署友好的仓库管理系统。设计背景、架构决策、路线图见 [docs/PLAN.md](docs/PLAN.md)，字段级数据模型见 [docs/data-model.md](docs/data-model.md)。

当前进度：**Phase 2 入库（Web）已完成**——采购单 → 收货 → 上架全流程、库存余额与流水查询；Phase 1 的主数据与鉴权权限框架。

## 目录结构

```
WMS/
├── apps/
│   ├── web/       React + TypeScript + Vite 前端
│   └── backend/   FastAPI + SQLAlchemy 后端
├── infra/
│   └── docker/    docker-compose 部署编排
└── docs/
    ├── PLAN.md        架构与路线图
    └── data-model.md  字段级数据模型
```

## 开发环境要求

- Node.js（已验证 26.x）
- Python 3.15（已验证）。Windows 上 `python` 命令可能指向 Microsoft Store 的占位程序，请用 `py` 启动器
- Docker Desktop（本地跑 SQL Server 容器）
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- C/C++ 编译工具（pyodbc、PyYAML 在 Python 3.15 上暂无预编译包，pip 会从源码构建）

## 第一次启动

### 1. 启动数据库并建库

```powershell
cd infra/docker
docker compose up -d db
```

容器不会自动建业务库，用任意 SQL 客户端连 `localhost,1433`（sa / `YourPassword123!`）执行一次：

```sql
IF DB_ID('wms') IS NULL CREATE DATABASE wms
```

### 2. 后端

```powershell
cd apps/backend
py -3.15 -m venv .venv
.venv\Scripts\Activate.ps1
pip install --prefer-binary -r requirements.txt
Copy-Item .env.example .env          # 按需修改数据库连接串
alembic upgrade head                 # 建表
$env:SEED_ADMIN_PASSWORD = "Admin@123"
python -m scripts.seed               # 初始化租户/权限/管理员/计量单位，可重复执行
uvicorn app.main:app --reload
```

API 文档：`http://localhost:8000/docs`，默认管理员账号 `admin`，密码为 `SEED_ADMIN_PASSWORD` 设置的值。

新增或修改模型后生成迁移：`alembic revision --autogenerate -m "说明"`，再 `alembic upgrade head`。

## 前端启动

```powershell
cd apps/web
npm install
npm run dev
```

默认 `http://localhost:5173`，开发模式下 `/api` 会被 Vite 代理到 `http://localhost:8000`。

## 用 Docker Compose 一键起（含 SQL Server 容器）

```powershell
cd infra/docker
docker compose up --build
```

## 当前已实现的 API（Phase 1 范围）

- `POST /api/v1/auth/login` — 登录换 JWT
- `GET/POST/PUT/DELETE /api/v1/business-partners` — 业务伙伴（客户/供应商）
- `GET/POST/PUT/DELETE /api/v1/items` — 商品主数据
- `GET/POST/PUT/DELETE /api/v1/locations` — 仓位（自引用树）
- `GET/POST /api/v1/users` — 用户（含角色分配）
- `GET /api/v1/uoms` — 计量单位
- `/api/v1/purchase-orders` — 采购单：列表/新建/详情/修改(草稿)，`/{id}/confirm`、`/{id}/cancel`、`/{id}/close`
- `/api/v1/grns` — 收货单：列表(可按 `po_id` 筛)/新建/详情，`/{id}/post`、`/{id}/cancel`
- `/api/v1/putaways` — 上架单：列表(可按 `grn_id` 筛)/新建/详情，`/{id}/post`、`/{id}/cancel`
- `GET /api/v1/stock/balances`、`GET /api/v1/stock/ledger` — 库存余额与流水

状态流转、并发控制规则见 [docs/data-model.md](docs/data-model.md) 第 8 节。

还没有：角色/权限管理 API；计量单位和单位换算(`item_uom_conversion`)的维护 API（目前只能直接写库，所以界面上下单只能用商品的基本单位，或已在库里配好换算的单位）；出库等 Phase 3+ 模块；移动端项目。

## SQL Server 方言注意事项

开发中已经踩过的坑，写新模型/查询时注意：
- **文本列一律用 `Unicode(n)`（NVARCHAR），不要用 `String(n)`**：`String` 在 SQL Server 生成 VARCHAR，默认排序规则下中文会被存成 `???`
- 布尔过滤不要用 `.is_(False)`（会生成 SQL Server 不支持的 `IS 0`），用 `== false()`
- 分页 `.offset()` 必须配 `.order_by()`
- 新增模型后要在 `app/models/__init__.py` 里导入，否则运行时外键找不到被引用的表
- 行锁用 `.with_hint(Model, "WITH (UPDLOCK, ROWLOCK)", "mssql")`，配 `populate_existing=True` 确保拿到加锁后的最新值（见 `services/document_common.py`）
- `SessionLocal` 关闭了 autoflush：同一事务内先改后查，记得先 `db.flush()`

## 前端注意事项

- React Query 的 `onError` 用 `showError`（`src/api/errors.ts`），不要写 `(e) => message.error(...)`：antd 的 message 返回值会被等待到提示框关闭，按钮会在出错后再转圈约 3 秒且点击无效
- 单据录入表单加 `onKeyDown={preventEnterSubmit}`：扫码枪每次扫描都带回车，不能让回车直接提交单据
- 开发模式下 antd 表单偶尔会在控制台打印 "There may be circular references"，这是 rc-field-form 比较字段元数据时的误报，与业务代码无关
