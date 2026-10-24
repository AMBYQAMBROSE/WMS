# WMS

多租户/多部署友好的仓库管理系统。设计背景、架构决策、路线图见 [docs/PLAN.md](docs/PLAN.md)，字段级数据模型见 [docs/data-model.md](docs/data-model.md)。

当前进度：**Phase 1 地基骨架**（主数据 business_partner/item/location + 鉴权权限框架 + 单据/库存表仅建表占位）。

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

## 本机环境说明

> 在这台机器上写这套骨架时检测到 **Node.js、Python（可执行的）、Docker、Git 均未安装**，所以下面的命令还没有被跑过验证，只是按工具的标准用法给出。正式开发前请先装好：
> - [Node.js](https://nodejs.org/)（LTS，建议 20.x）
> - [Python](https://www.python.org/)（3.12，注意不要用 Microsoft Store 里那个占位版本）
> - [Docker Desktop](https://www.docker.com/products/docker-desktop/)（跑 SQL Server 容器用）
> - [Git](https://git-scm.com/)
> - 一个能连 SQL Server 的 [ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)（本机直接跑后端、不用 Docker 时需要）

装好之后告诉我，我可以帮你跑通第一次启动、修掉环境相关的报错。

## 后端启动（本机直接跑，不用 Docker）

```powershell
cd apps/backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # 按需修改数据库连接串
alembic revision --autogenerate -m "init"
alembic upgrade head
uvicorn app.main:app --reload
```

API 文档：`http://localhost:8000/docs`

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

还没有：角色/权限的管理 API（目前只能直接在数据库里插数据做种子）、入库/出库/库存等 Phase 2+ 的模块、移动端项目。

## 还需要你补上的东西

1. **种子数据脚本**：目前 `tenant`、`permission`、`role` 等表还没有初始化数据的脚本，第一次跑起来需要手动插入至少一个 tenant + 一个管理员角色（挂上全部 permission）+ 一个管理员 user，否则登录不了。下次让我继续写一个 `scripts/seed.py` 可以直接解决。
2. **Alembic 首个迁移**：`alembic revision --autogenerate` 需要连上一个真实的 SQL Server 才能生成，这台机器现在连不上，等环境装好后第一次跑的时候生成。
