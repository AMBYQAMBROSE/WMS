# WMS 系统开发计划

> 参考对象：`C:\Ninso\94weijun\Ninso`（ASP.NET MVC WMS，面向 FMCG/经销商仓库）
> 目标栈：React (TypeScript) + Python (FastAPI) + SQL Server
> 核心要求：业务流程顺畅可用，同时做到**多租户/可配置**，方便套用到不同公司而不需要改代码

---

## 1. 设计原则

1. **流程对齐 Ninso，命名去行业化**：Ninso 的模块命名贴合它自己客户的业务术语（如 `Outlet`、`Tool`、`PMA`）。新系统保留流程语义，但用通用词汇建模（见第 4 节),方便换客户时只改配置/翻译，不改表结构。
2. **配置驱动而非代码分支**：不同公司的差异（单号规则、是否启用 Cross-Dock/Repack、是否按批次/效期管理、审批层级、单据字段）通过**租户配置表 + Feature Flag + 动态表单**解决，不用 if-else 堆代码或拉分支。
3. **API-first**：所有业务动作都是后端 REST/RPC API，Web（React）、未来的 PDA/手机扫描端、第三方 ERP 集成都走同一套 API。
4. **单一库存真相来源**：所有库存变动（入库/上架/拣货/调整/盘点/移位）必须落一张统一的 `stock_ledger` 流水表，当前库存是流水的汇总视图，不允许多处直接改库存字段。
5. **先打地基，再长肌肉**：第一阶段把主数据、库存流水模型、权限/多租户框架做稳，后续模块都是在这个地基上加 CRUD + 流程状态机，边际成本会越来越低。

---

## 2. 从 Ninso 提炼的业务模块清单

对 `Controllers/`、`DataModels/`、`Views/` 做了扫描，Ninso 的业务范围大致是：

| 领域 | Ninso 对应功能 | 说明 |
|---|---|---|
| 主数据 | Item, Supplier, Outlet, UOM, PackingSpec, BinNum/BinType/Rack, Category, Division/Department | SKU、供应商、客户（outlet=门店/经销点）、仓位结构 |
| 采购入库 | PO, GRN/GR, StockIn, POShort, POReceivingStatus | 采购单 → 收货 → 短溢处理 |
| 上架/仓位 | InBin, MoveLocation, CombineLocation, BinNumLock, RackingUsage | 收货后上架、移位、锁仓位、使用率 |
| 越库/分货 | CrossDock, CrossDockSub, CrossDockReport | 越库直发，不进常规库位 |
| 重新包装 | Repack, RepackGR, RepackLoading, RepackItemSub | 原包拆分/重组再入库 |
| 库存管理 | SkuLedger, Adjustment, OpeningStock, ClosingStock | 库存流水、调整、期初/期末 |
| 盘点 | CycleCount, Stocktake, Audit, AuditVariance | 循环盘点、全盘、差异审核 |
| 补货 | Replenish, ReplenishStatus, DailyReplenish | 拣货区/前线补货 |
| 销售出库 | OutletOrder, OrderList, OrderShortage, SKUOOS | 客户订单、缺货处理 |
| 分配/拣货 | ManualAllocation, LoadingManualAllocation, Picking, PickList, PickerIndiKPI/GroupKPI | 库位分配 → 拣货 → 拣货员绩效 |
| 装车/出货 | NormalLoading, PickingCD, PrintPickingList | 装车清单、打印 |
| 退货 | ReturnNote, ReturnSupplier, GoodReturn, SupplierReturnLedger | 客户退货、供应商退货 |
| 工具/周转资产 | Tool, ToolOneMany, ToolManyOne, ToolReceive/Return | 栈板/篮子/推车等周转工具借还（可泛化为"可回收资产管理") |
| 报表/看板 | DashboardSummary, TurnOverReport, SupplierLedger, OutletLedger | 经营看板、周转率、对账单 |
| 系统/集成 | SystemConfiguration, User/Login, *ApiLog (Po/Grn/Do/Item/Customer) | 用户权限、与外部 ERP 的双向同步日志 |

**关键观察**：
- Ninso 大量使用 `XxxGetApiLog` / `XxxPostApiLog` 模式与外部 ERP 做异步对账同步 → 新系统应把"集成同步"抽成独立模块，而不是每个单据各写一套。
- `Outlet` 本质是"收货/配送对象"，`Supplier` 是"发货对象"——两者可以合并成一个 `BusinessPartner`（业务伙伴）表 + 角色标记，减少重复建模。
- `PO/GRN/SO/DO/Adjustment/Transfer` 本质都是"单据头+行+状态机"，可以用统一的单据框架承载，差异只在单据类型和状态流转规则。

---

## 3. 多租户 / 可配置化设计（重点）

这是让系统能套用到不同公司的核心机制。

### 3.1 租户隔离模型（已按"目标客户=大型企业 + 允许私有化部署"调整）

> 确认信息：暂无具体客户，但预期对象是**有一定规模的大厂**，且**允许客户私有化部署**。大厂通常自带 IT/数据安全要求，倾向于"一家公司一套独立环境"而不是和别家公司共用一个数据库。因此隔离策略的主次关系调整为：

- **主模型：单租户独立部署（Single-Tenant per Deployment）**。每个客户拿到的是一套独立部署（独立数据库实例、独立应用服务），可以部署在客户自己的机房/私有云，也可以是我们托管的独立环境。客户之间物理隔离，不存在"共用库靠过滤条件隔离"的安全风险，最符合大厂的数据安全审查习惯。
- **仍然保留 `tenant_id` 字段**（成本几乎为零，但保留灵活性）：
  - 方便内部做演示环境/测试环境里跑多套假租户数据；
  - 未来如果出现中小客户想用低成本的共享 SaaS 模式，代码不用改，直接把隔离策略从"独立部署"切换成"行级隔离"（SQL Server Row-Level Security）即可。
  - 即使是单租户部署，`tenant_id` 也天然对应"多仓库/多法人主体"的场景（大厂常见：一套系统管多个子公司/多个仓库），不会被浪费。
- **"能否套用到不同公司"的核心机制不再是运行时多租户，而是第 3.4 节的"部署模板 + 配置化"**：新客户签约后，走一套标准化脚本/流程快速拉起一套独立环境并套入默认配置，而不是把新客户塞进已有的共享实例。

### 3.1.1 私有化部署对架构的影响

> 确认信息：客户网络环境**通常以内部网络为主、不对外**（即部署在客户内网，不暴露公网）；具体细节（能否联网、是否有K8s、SQL Server实例由谁提供等）等有具体客户时再一起规划，当前先按"内网优先、离线可用"做保守假设，不假设有公网/云服务可用。

- **打包方式**：用 Docker Compose（默认）打一套"前端+后端+队列+反向代理"镜像，SQL Server 可选"客户已有实例"或随包提供的容器化实例；复杂客户若有 K8s 能力，额外提供 Helm Chart。
- **离线/内网环境**：默认假设内网隔离、无/弱互联网访问，安装包需要支持离线镜像导入（`docker save/load`），运行时不依赖任何需要联网才能用的外部服务（如云端日志/监控/第三方API），这类能力都做成可选、默认关闭。
- **升级机制**：版本升级 = 新镜像 + Alembic 数据库迁移脚本，要支持"客户自己按文档升级"或"我们远程/驻场升级"两种模式，升级脚本必须可回滚。
- **License/合规**：**先跳过**，当前不投入做授权文件/用量控制机制。设计上只需注意不要写死"必须联网校验"之类的硬编码，保留以后要加时能加的余地即可，不现在花时间实现。
- **企业身份集成（AD/LDAP/SSO）**：**先跳过**，当前用系统自带的账号+角色体系（见 3.3 RBAC）即可。只需要在用户模型上不要做"强绑定本地密码"的假设（比如密码字段允许为空、登录方式做成可扩展的 provider 字段），方便以后加对接而不用改表结构，但协议选型和具体对接开发本阶段不做。

### 3.2 可配置项分层
| 层级 | 内容 | 存储方式 |
|---|---|---|
| 租户基础配置 | 公司信息、LOGO、时区、默认语言、计量单位制 | `tenant_settings` 表 |
| 功能开关 (Feature Flags) | 是否启用 Cross-Dock / Repack / 批次管理 / 效期管理 / 序列号 / 周转资产管理 / 多仓多库区 | `tenant_feature_flags` 表，后端按租户读取后决定展示哪些菜单/校验规则 |
| 单号规则 | PO/GRN/SO/DO 等单号前缀、长度、是否按年月重置 | `doc_number_rule` 表，模板如 `{PREFIX}-{YYYYMM}-{SEQ:6}` |
| 业务规则参数 | 出库策略（FIFO/FEFO/LIFO）、是否允许超发、盘点频率、安全库存阈值 | `tenant_business_rules`（JSON 字段存放可扩展参数，核心字段结构化） |
| 审批流 | 采购/调整/退货是否需要审批，审批层级 | `approval_workflow` + `approval_step`，用简单状态机引擎驱动 |
| 自定义字段 | 不同公司对 Item/客户/单据可能需要额外字段（如保质期天数、冷链温区） | EAV 模式的 `custom_field_definition` + `custom_field_value`，避免为每个客户改表结构 |
| UI/表单定制 | 列表显隐列、必填项、下拉选项 | 前端读取"表单 Schema"（JSON）渲染，而不是硬编码表单 |

### 3.3 角色与权限
- RBAC：`role` → `permission`（按模块+操作粒度，如 `grn.create`, `picking.confirm`）。
- 权限矩阵可按租户自定义角色（如有的客户要"拣货主管"角色，有的不需要），但权限点（permission code）是系统级固定的，保证代码里判断逻辑不随租户变化。

### 3.4 "行业模板"机制
为了快速套用到新公司，设计 **部署模板（Industry Preset）**：首次给新客户开通时，选择模板（如"快消品经销"、"3PL 代运营"、"冷链仓"），自动写入一套默认 Feature Flag + 单号规则 + 角色权限 + 基础主数据（UOM、调整原因代码等），再由实施人员微调，而不是从零配置。

---

## 4. 技术架构

### 4.1 前端 — React
- **React 18 + TypeScript + Vite**
- UI 组件库：建议 **Ant Design**（表格/表单密集型后台场景成熟度高，内置国际化），搭配自定义主题变量实现"每租户换色换 LOGO"
- 状态管理：**TanStack Query**（服务端数据/缓存/重试）+ **Zustand or Redux Toolkit**（少量全局 UI 状态，如当前租户、当前用户）
- 路由：React Router，按权限动态生成菜单（菜单本身也是后端返回的数据驱动，不是前端硬编码）
- 表单：React Hook Form + Zod 校验，表单字段支持从后端 Schema 动态生成（配合 3.2 的自定义字段）
- 国际化：i18next（至少中/英文，预留扩展）
- 扫码/硬件对接：
  - 浏览器端优先支持"键盘输入型"扫码枪（USB/BT HID 模式，直接当输入框文本）
  - 预留 WebUSB/WebSerial 或原生 PDA（Android + 浏览器/WebView）扫码 SDK 对接接口
  - 标签打印走后端生成 PDF/ZPL，前端触发打印任务
- 构建产物：按模块做路由级代码分割（lazy load），减少首屏加载

### 4.2 移动端 / PDA（确认需要）

大厂仓库现场作业（收货、上架、拣货、盘点、移位）离不开手持设备扫码，这是独立于 Web 后台的一条开发线，但**复用同一套后端 API**。

- **技术选型：React Native**（与 Web 共享 TypeScript 技能栈、部分业务逻辑/类型定义可通过 `packages/shared-types` 复用）。已确认扫码方案走键盘模拟模式（见下），不需要对接任何硬件厂商原生 SDK，所以不需要原生 Android 壳，React Native 可以覆盖全部需求。
- **扫码输入方案：确定走键盘模拟模式（HID/DataWedge）**：扫码枪/工业机扫码后直接当文本输入，App 用一个隐藏聚焦的输入框接收即可。兼容性最好、不绑定具体硬件品牌，也不需要集成任何厂商原生 SDK，开发和维护成本最低。暂不考虑原生扫码 SDK（持续扫描、震动反馈等增强体验），除非未来有客户明确要求且硬件已选定，再单独评估。
- **离线优先（Offline-first）设计**：仓库内网/弱网盲区常见，App 端需要：
  - 本地队列缓存未提交的扫描动作（本地 SQLite/MMKV），网络恢复后自动重试提交；
  - 关键主数据（SKU、仓位）做本地缓存+定期同步，避免扫码时还要等接口加载。
- **功能范围（现场高频动作，优先做移动端）**：收货确认、上架确认、拣货确认、盘点扫描、移位确认、周转资产借还扫描。报表/配置类操作留在 Web 后台，不做到移动端。
- **节奏**：移动端不需要和 Web 同时起步，建议在对应 Web 模块（收货/库存/出库）的 API 稳定后紧跟启动，而不是一开始就两端并行写，避免 API 返工。

### 4.3 后端 — Python
- **FastAPI**（异步、自动 OpenAPI 文档、Pydantic 校验，天然适合给 React 前端 + 未来 PDA 端提供统一 API）
- ORM：**SQLAlchemy 2.0 + Alembic**（迁移管理）
- 数据校验/序列化：Pydantic v2 Schema，严格区分 `Create / Update / Read` DTO
- 分层架构：
  ```
  api/        路由层（仅做参数校验+调用service+返回）
  services/   业务逻辑层（事务边界、状态机、规则引擎）
  repositories/ 数据访问层（SQLAlchemy 查询封装）
  models/     ORM 模型
  schemas/    Pydantic DTO
  core/       租户中间件、权限中间件、配置中心、异常处理
  tasks/      异步任务（Celery/RQ）
  ```
- 鉴权：JWT（Access + Refresh），租户信息和权限编码放进 Token Claims；后续可接 SSO/AD/LDAP（大客户常见需求）
- 异步任务队列：**Celery + Redis**（或 RQ，视团队熟悉度），用于：
  - 与外部 ERP 的异步同步（参考 Ninso 的 ApiLog 模式，但改成统一的 `integration_job` + `integration_log` 表，而不是每个单据一张日志表）
  - 批量导入导出（Excel）、报表生成、标签/单据打印排队
- 多租户中间件：请求进来先解析 Token → 得到 tenant_id → 注入到数据库会话上下文，所有 Repository 查询自动带租户过滤（类似 SQLAlchemy 的 `with_loader_criteria` 或自定义 Session 事件）
- API 风格：REST 为主（资源化：`/api/v1/purchase-orders`），对"拣货确认""扫码"等强动作型操作用显式的 action 端点（`/picking-tasks/{id}/confirm`），避免滥用 PATCH 表达状态流转

### 4.4 数据库 — SQL Server
- 使用 SQL Server 的 **Row-Level Security (RLS)** 做租户隔离兜底（即使应用层漏加 tenant_id 过滤，数据库层也拦住）
- 所有表统一审计字段：`id (uniqueidentifier/bigint)`, `tenant_id`, `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`（软删除）
- 单据类表统一"头+行"结构（见第 5 节）
- 库存并发控制：拣货/上架/盘点等高并发场景用**乐观锁（rowversion 字段）**或行级锁，避免库存超卖
- 索引策略：SKU+仓位+批次的组合索引是热点，提前设计好覆盖索引
- 历史数据：大表（stock_ledger, pick_task）按时间分区或定期归档到历史表，避免越用越慢

### 4.5 集成层（当前无明确需求，按"框架先留位、实现延后"处理）
- 统一的 `integration_connector` 配置（每租户可配多个外部系统：ERP/财务/TMS）
- 统一的 `integration_job`（任务）+ `integration_log`（每次调用的请求/响应/状态），替代 Ninso 中每个单据各一张 ApiLog 表的做法
- 对外提供 Webhook/回调机制，方便客户自己的系统订阅"GRN 完成""DO 已发货"等事件
- **优先级说明**：目前没有具体客户、也没有明确要对接的外部系统，所以本阶段只需要把这个"可插拔集成框架"的壳子设计出来（表结构 + 预留的 Job/Log 机制），具体连接器（如 SAP/用友/金蝶 Connector）**不在初期开发范围**，等有客户明确了对接系统后再按需实现，避免猜测性开发。大厂几乎必然已有 ERP，这块预计迟早会用到，所以框架要留位，但不急着填实现。

### 4.6 部署与基础设施
- **默认形态：Docker Compose 打包，一客户一独立环境**（见 3.1.1），可部署在客户私有机房/私有云，也可我方托管；有 K8s 能力的客户额外提供 Helm Chart，架构上不绑定具体部署方式
- 支持**离线安装包**（镜像导出/导入），适配大厂内网隔离、无外网访问的场景
- CI/CD：Lint + 单元测试 + 集成测试 + 自动迁移 + 构建镜像 → 产出"可交付安装包"（而不只是部署到我方云环境）
- 环境分层：dev / staging / 每客户独立 production
- 升级与回滚：版本号化的 Alembic 迁移脚本 + 镜像 tag，提供客户自助升级手册和回滚方案
- 日志/监控：结构化日志（含 tenant_id 便于按租户/按部署排查）、APM（如 OpenTelemetry，私有化部署下默认关闭外发，仅本地落盘）、库存异常报警

---

## 5. 数据模型设计原则（通用化）

| 通用表 | 替代 Ninso 中的 | 说明 |
|---|---|---|
| `business_partner` (+ `type`: customer/supplier) | `Outlet`, `Supplier` | 合并客户与供应商，角色字段区分，避免重复字段 |
| `location` (warehouse > zone > aisle > rack > bin，自引用树或路径表) | `BinNum`, `Rack`, `BinType`, `AreaView` | 仓位结构通用化，支持任意层级 |
| `item` + `item_attribute`（批次/效期/序列号开关） | `Item`, `BarcodeItem`, `PackingSpec` | SKU 主数据，按租户 Feature Flag 决定是否启用批次/效期字段校验 |
| `document_header` + `document_line`（`doc_type`: PO/GRN/SO/DO/ADJUST/TRANSFER/RETURN） | PO/GRN/OutletOrder/NormalLoading/Adjustment/ReturnNote 等各自建表 | 单据主框架统一，具体业务字段走扩展表或 JSON 扩展列，减少重复的头行表 |
| `stock_ledger`（唯一库存流水） | `SkuLedger`, `ClosingStock`, `OpeningStock` | 所有库存增减的唯一入口，当前库存=汇总视图或物化汇总表 `stock_balance` |
| `task`（拣货/补货/盘点/移位任务统一抽象，`task_type` 区分） | `PickList`, `Replenish`, `CycleCount`, `MoveLocation` | 仓内执行类任务共用分配/状态/操作人字段 |
| `returnable_asset` + `returnable_asset_transaction` | `Tool`, `ToolOneMany`, `ToolManyOne` | 泛化为"周转资产"（栈板/笼车/托盘），不是所有客户都需要，走 Feature Flag |
| `kpi_snapshot` / 报表走只读视图或 OLAP 层 | `PickerIndiKPI`, `TurnOverReport` | 报表尽量不额外建业务表，用视图/定时汇总表 |

> 设计取舍说明：`document_header/line` 统一框架能减少重复建模，但会牺牲一些单表字段的强类型约束；建议核心高频单据（PO、GRN、SO、DO、库存调整）用统一框架 + 类型化的"扩展明细表"（1:1 关联，只放该单据类型特有字段），兼顾灵活性与查询性能。

---

## 6. 核心业务流程（状态机示意）

对齐 Ninso 流程，但用统一术语描述，方便后续做"客户A流程" vs "客户B流程"的配置差异对比：

1. **采购入库**：`PO 创建 → 审批(可配) → 收货GRN(全部/部分/短溢) → 质检(可配) → 上架 → 入库完成`
2. **越库/直发**（可选模块）：`PO/GRN 中标记越库 SKU → 不进常规库位 → 直接生成出库任务`
3. **库内移动**：`移位 / 合并库位 / 补货(从大库位到拣货位)`
4. **盘点**：`循环盘点任务生成 → 盘点员扫描 → 差异产生 → 审核 → 库存调整落账`
5. **销售出库**：`销售订单接收(API/手工) → 缺货检查 → 库位分配(自动/手动) → 拣货任务生成 → 拣货确认 → 复核/打包(可配) → 装车 → 出库单(DO)完成 → 库存扣减`
6. **退货**：`客户退货 → 质检分类(可用/报损) → 入库 or 报损 → 供应商退货(反向流程)`
7. **周转资产**（可选模块）：`借出登记 → 对账 → 归还登记 → 逾期提醒`
8. **系统集成**：`外部ERP订单/物料 Pull → 本地处理 → 完成结果 Push 回ERP`，所有步骤落 `integration_log` 便于追溯重试

每个状态机用一张 `workflow_definition`（租户可覆盖默认流程，比如客户A要求GRN必须质检，客户B不需要）驱动，而不是写死在代码分支里。

---

## 7. 非功能需求清单

- **权限与审计**：所有写操作留审计日志（谁在什么时间改了什么，改之前的值），满足客户合规审计需求
- **多语言**：界面文案、单据打印模板支持多语言
- **性能**：拣货/收货高峰并发写入库存流水表要做压测，目标单仓日处理量设定后反推数据库索引/分区策略
- **离线/弱网**：仓库 Wi-Fi 常有盲区，PDA/扫码端需考虑短暂离线缓存后重试提交
- **可观测性**：关键业务指标（订单处理时效、拣货准确率、库存准确率）要能从日志/数据自动生成，不需要额外重复开发报表基础设施
- **企业身份集成（AD/LDAP/SSO）、License/用量控制**：已确认当前阶段**先跳过**，不投入开发；只在数据模型上保留扩展余地（见 3.1.1），不做具体实现

---

## 8. 项目结构建议（Monorepo）

```
WMS/
├── apps/
│   ├── web/              # React 前端
│   └── backend/           # FastAPI 后端
├── packages/
│   ├── shared-types/      # 前后端共享的类型定义(OpenAPI生成)
│   └── ui-kit/             # 公司通用UI组件/主题
├── infra/
│   ├── docker/
│   ├── k8s/ (可选)
│   └── migrations/        # Alembic
├── docs/
│   ├── PLAN.md            # 本文件
│   ├── data-model.md
│   └── api-spec/ (OpenAPI导出)
└── scripts/                # 租户初始化、模板导入等脚本
```

---

## 9. 阶段路线图

由于暂无具体签约客户，但明确目标是大型企业 + 允许私有化部署 + 需要移动端，路线图按"先把可复用的地基和部署能力做扎实，再铺业务模块"排序，Web 与移动端对同一模块错位并行（移动端紧跟对应 Web 模块的 API 稳定之后启动）：

| 阶段 | 目标 | 产出 |
|---|---|---|
| **Phase 0 — 需求与建模**（1-2周） | 梳理通用数据模型与 API 草案；同步明确企业级非功能需求（AD/SSO 期望、私有化部署的典型 IT 环境假设、License 是否需要） | 数据模型、租户/部署配置项清单、OpenAPI 草案 |
| **Phase 1 — 地基**（3-4周） | 鉴权权限(含 AD/SSO 扩展点)、主数据模块(business_partner/item/location)、单据框架骨架、部署打包(Docker Compose)跑通一次"从零拉起环境" | 可登录、可建主数据、一套可离线安装的最小可运行环境 |
| **Phase 2 — 入库 Web**（2-3周） | PO → GRN → 上架 全流程 | 入库闭环可用 |
| **Phase 2.5 — 移动端收货/上架**（1-2周，紧随Phase2） | React Native（或评估后的技术方案）跑通扫码收货+上架，验证硬件扫码兼容性与离线队列设计 | 移动端技术路线定型，可作为后续模块模板 |
| **Phase 3 — 库存 Web + 移动端**（2-3周） | 库存流水、调整、移位、循环盘点；移动端覆盖盘点/移位扫描 | 库存准确性可验证，现场盘点可脱离纸单 |
| **Phase 4 — 出库 Web + 移动端**（3-4周） | 订单 → 分配 → 拣货 → 装车 → DO；移动端覆盖拣货确认 | 出库闭环可用，含拣货KPI |
| **Phase 5 — 扩展模块**（按需） | Cross-Dock / Repack / 退货 / 周转资产，按 Feature Flag 启停 | 可选模块上线 |
| **Phase 6 — 私有化部署标准化**（2周，可与Phase2-4并行打磨） | 把"一客户一环境"的交付流程走通：安装文档、离线镜像包、升级/回滚脚本、(可选)License 机制 | 新客户从签约到环境可用的标准作业流程(SOP)，耗时可量化 |
| **Phase 7 — 集成框架与报表**（框架先行，连接器延后） | 集成任务/日志表结构、Webhook 机制骨架、经营看板；具体 ERP Connector 待客户明确后再开发 | 集成留好扩展位，看板可用 |
| **Phase 8 — UAT / 首个客户试运行** | 性能压测、培训、在首个私有化环境灰度上线 | 正式投产，反哺 Phase 6 的 SOP 完善 |

---

## 10. 待确认事项

### 已确认（2026-10-24）
1. 暂无具体签约客户，但目标客户群体是**有一定规模的大厂** → 架构按企业级要求设计（独立部署、强权限审计、可对接企业身份系统），压测目标待签约后用真实 SKU 数/日单量反推。
2. **不需要**兼容/迁移 Ninso 历史数据 → 路线图中已移除 ETL 迁移任务。
3. **需要**移动端/PDA → 已在 4.2 节给出技术方案(React Native 优先，视硬件 SDK 需求再评估原生)，并入 Phase 2.5/3/4 并行开发。
4. **没有**现成外部 ERP/财务系统要在第一阶段打通 → 集成模块降级为"框架先行，连接器延后"（见 4.5 节、Phase 7）。
5. **允许客户私有化部署** → 隔离策略从"共享库多租户"调整为"单租户独立部署为主"（见 3.1 节），部署打包/离线安装/升级机制纳入 Phase 6 作为正式交付物。

### 已确认（2026-10-24 第二轮）
6. **移动端扫码方案**：确定走**键盘模拟扫码（HID/DataWedge）**，不集成任何硬件厂商原生 SDK → 4.2 节已更新，移动端技术选型可以直接定为 React Native，不留分支方案。
7. **私有化部署的网络假设**：客户环境**通常以内部网络为主、不对外**，具体细节（能否联网、K8s能力、SQL Server实例由谁提供）等有具体客户后再一起规划 → 3.1.1 节已按"内网优先、离线可用、不依赖联网校验"的保守假设调整架构。
8. **License/授权机制**：**先跳过**，不在当前阶段投入开发。
9. **企业身份集成（AD/LDAP/SSO）**：**先跳过**，当前用系统自带账号体系，只在用户模型上留扩展字段。

### 仍需在正式启动前敲定
1. **首个落地客户的行业与规模**：一旦有意向客户，建议马上补一轮 Phase 0 现场调研（具体流程差异、SKU/单量级、现有系统现状、该客户网络/服务器环境的实际约束），用真实数据校准本计划里的保守假设。这是目前唯一还悬而未决、且会实质影响优先级排序的问题，其余技术选型已基本定型，可以开始 Phase 1 地基开发。

---

> 本文档不含代码，用于确定架构方向与模块范围。建议在动手写代码前，先用 Phase 0 的结果对本文档做一轮确认/调整。
