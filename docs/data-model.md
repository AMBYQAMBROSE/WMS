# 数据模型设计（Phase 1 — 字段级）

> 对应 [PLAN.md](PLAN.md) 第 5 节的设计原则落地到具体字段。本阶段只覆盖 Phase 1 范围：租户/权限、主数据(business_partner/item/location)、单据框架骨架。入库/库存/出库各单据的专属字段在对应 Phase 补充。
>
> 命名约定：表名 `snake_case` 单数；主键统一 `id`；外键 `xxx_id`；所有业务表都带「公共审计字段」（见 0 节），不再逐表重复列出。

---

## 0. 公共基类字段（所有业务表都有，ORM 用 Mixin 实现）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `uniqueidentifier` | 主键，应用层生成 UUID |
| `tenant_id` | `uniqueidentifier` | 所属租户/子公司（单租户部署下通常只有一行 tenant，但字段保留，见 PLAN.md 3.1） |
| `created_at` | `datetime2` | 创建时间 |
| `created_by` | `uniqueidentifier` (FK→user.id，可空) | 创建人 |
| `updated_at` | `datetime2` | 最后更新时间 |
| `updated_by` | `uniqueidentifier` (FK→user.id，可空) | 最后更新人 |
| `is_deleted` | `bit` default 0 | 软删除标记 |
| `row_version` | `int` default 0 | 乐观锁版本号，每次更新 +1 |

---

## 1. 租户与系统配置

### `tenant`
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | uniqueidentifier | PK |
| `code` | nvarchar(50) | 租户编码，唯一 |
| `name` | nvarchar(200) | 公司/子公司名称 |
| `default_locale` | nvarchar(10) | 默认语言，如 `zh-CN` |
| `default_timezone` | nvarchar(50) | 如 `Asia/Shanghai` |
| `is_active` | bit | 是否启用 |

### `tenant_feature_flag`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `feature_code` | nvarchar(100) | 如 `CROSS_DOCK`、`BATCH_MGMT`、`EXPIRY_MGMT`、`SERIAL_MGMT`、`RETURNABLE_ASSET` |
| `is_enabled` | bit | |

唯一约束：`(tenant_id, feature_code)`

### `doc_number_rule`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `doc_type` | nvarchar(30) | 如 `PO`、`GRN`、`SO`、`DO`、`ADJUST` |
| `prefix` | nvarchar(20) | |
| `pattern` | nvarchar(100) | 模板，如 `{PREFIX}-{YYYYMM}-{SEQ:6}` |
| `current_seq` | bigint | 当前序号（按需按年月重置，由服务层逻辑处理） |

### `custom_field_definition`（EAV，Phase 1 先建表，暂不接入 UI）
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `entity_name` | nvarchar(50) | 如 `item`、`business_partner` |
| `field_key` | nvarchar(100) | |
| `label` | nvarchar(100) | |
| `data_type` | nvarchar(20) | `string/number/date/bool/enum` |
| `is_required` | bit | |
| `options_json` | nvarchar(max) | enum 选项等 |

### `custom_field_value`
| 字段 | 类型 | 说明 |
|---|---|---|
| `definition_id` | FK→custom_field_definition | |
| `entity_id` | uniqueidentifier | 指向具体记录（item.id 等） |
| `value_text` | nvarchar(max) | 统一存文本，由应用层按 data_type 解析 |

---

## 2. 用户与权限（RBAC）

### `user`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `username` | nvarchar(100) | 唯一（同租户内） |
| `display_name` | nvarchar(100) | |
| `email` | nvarchar(200) | 可空 |
| `password_hash` | nvarchar(255) | **可空**（预留未来接 SSO/AD 时可以没有本地密码） |
| `auth_provider` | nvarchar(20) default `'local'` | 预留字段：`local` / `ad` / `saml` / `oidc`，当前只实现 `local` |
| `is_active` | bit | |
| `last_login_at` | datetime2 | 可空 |

### `role`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `code` | nvarchar(50) | 如 `WAREHOUSE_MANAGER`、`PICKER`，同租户内唯一 |
| `name` | nvarchar(100) | |
| `is_system` | bit | 系统预置角色不可删除 |

### `permission`（系统级固定清单，不分租户，代码里按模块+操作定义，如 `grn.create`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | nvarchar(100) | PK，如 `grn.create` / `picking.confirm` |
| `module` | nvarchar(50) | 如 `inbound` |
| `description` | nvarchar(200) | |

### `role_permission`（关联表）
| 字段 | 类型 |
|---|---|
| `role_id` | FK→role |
| `permission_code` | FK→permission.code |

### `user_role`（关联表，支持一人多角色）
| 字段 | 类型 |
|---|---|
| `user_id` | FK→user |
| `role_id` | FK→role |

---

## 3. 主数据

### `business_partner`（合并 Ninso 的 Outlet / Supplier）
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `code` | nvarchar(50) | 唯一（同租户内） |
| `name` | nvarchar(200) | |
| `partner_type` | nvarchar(20) | `customer` / `supplier` / `both` |
| `contact_name` | nvarchar(100) | 可空 |
| `contact_phone` | nvarchar(50) | 可空 |
| `address` | nvarchar(400) | 可空 |
| `is_active` | bit | |

### `uom`（计量单位）
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `code` | nvarchar(20) | 如 `EA`、`CTN`、`PLT` |
| `name` | nvarchar(50) | |

### `item`（SKU 主数据）
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `sku_code` | nvarchar(50) | 唯一（同租户内） |
| `barcode` | nvarchar(50) | 可空，可多码见 `item_barcode` |
| `name` | nvarchar(200) | |
| `category` | nvarchar(100) | 可空，Phase1 先用简单字符串，分类树留作后续增强 |
| `base_uom_id` | FK→uom | 基本计量单位 |
| `is_batch_managed` | bit | 是否按批次管理（受 tenant feature flag 影响，但落在 item 行上方便单品覆盖） |
| `is_expiry_managed` | bit | 是否管理效期 |
| `is_serial_managed` | bit | 是否管理序列号 |
| `shelf_life_days` | int | 可空，效期管理时使用 |
| `is_active` | bit | |

### `item_barcode`（一品多码）
| 字段 | 类型 |
|---|---|
| `item_id` | FK→item |
| `barcode` | nvarchar(50) |
| `uom_id` | FK→uom（该条码对应的包装单位，如整箱码/单件码） |

### `item_uom_conversion`（单位换算，如 1 CTN = 12 EA）
| 字段 | 类型 |
|---|---|
| `item_id` | FK→item |
| `from_uom_id` | FK→uom |
| `to_uom_id` | FK→uom |
| `factor` | decimal(18,6) |

---

## 4. 仓位结构（`location` 自引用树，替代 Ninso 的 BinNum/Rack/BinType）

### `location`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `code` | nvarchar(50) | 仓位编码，同租户内唯一 |
| `name` | nvarchar(100) | |
| `location_type` | nvarchar(20) | `WAREHOUSE` / `ZONE` / `AISLE` / `RACK` / `BIN` |
| `parent_id` | FK→location（可空，顶层仓库为空） | 自引用，形成层级树 |
| `path` | nvarchar(400) | 物化路径，如 `/WH01/ZONE-A/AISLE-01/BIN-003`，便于按前缀快速查某仓库/区域下所有仓位 |
| `is_pickable` | bit | 是否可被拣货分配（区分存储位/拣货位） |
| `is_locked` | bit | 锁位（对应 Ninso BinNumLock） |
| `capacity_qty` | decimal(18,4) | 可空，容量上限（按基本单位） |
| `is_active` | bit | |

> Phase 1 只建表结构和基础 CRUD；仓位使用率、容量校验等规则在 Phase 2/3 结合库存模块实现。

---

## 5. 单据框架骨架（Phase 1 只搭骨架，具体类型字段在对应 Phase 补）

### `document_header`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `doc_type` | nvarchar(30) | `PO`/`GRN`/`SO`/`DO`/`ADJUST`/`TRANSFER`/`RETURN`... |
| `doc_no` | nvarchar(50) | 按 `doc_number_rule` 生成，唯一（同租户+doc_type内） |
| `status` | nvarchar(30) | 状态机当前状态，具体枚举值由 `doc_type` 决定 |
| `partner_id` | FK→business_partner（可空） | 往来对象（供应商/客户），Adjustment 等单据可为空 |
| `remark` | nvarchar(400) | 可空 |

### `document_line`
| 字段 | 类型 | 说明 |
|---|---|---|
| `document_id` | FK→document_header | |
| `line_no` | int | 行号 |
| `item_id` | FK→item | |
| `uom_id` | FK→uom | |
| `qty_planned` | decimal(18,4) | 计划数量（下单量/应收量等） |
| `qty_actual` | decimal(18,4) | 实际数量（实收/实拣等），默认 0 |
| `location_id` | FK→location（可空） | 目标/来源仓位，视单据类型而定 |

> 各具体单据类型的专属字段（如 GRN 的质检结果、PO 的采购价）在对应 Phase 用「1:1 扩展表」承载，例如 `grn_line_ext(document_line_id FK, qc_result, ...)`，Phase 1 不预先建，避免猜测字段。

---

## 6. 库存流水骨架（Phase 1 建表占位，Phase 3 实现业务逻辑）

### `stock_ledger`
| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | FK→tenant | |
| `item_id` | FK→item | |
| `location_id` | FK→location | |
| `batch_no` | nvarchar(50) | 可空 |
| `expiry_date` | date | 可空 |
| `qty_change` | decimal(18,4) | 正数入、负数出 |
| `movement_type` | nvarchar(30) | `RECEIVE`/`PUTAWAY`/`PICK`/`ADJUST`/`MOVE`/`COUNT`... |
| `ref_document_line_id` | FK→document_line（可空） | 关联到触发这条流水的单据行 |
| `occurred_at` | datetime2 | 业务发生时间（可能晚于 created_at） |

### `stock_balance`（汇总视图或定时物化表，Phase 1 先占位不实现刷新逻辑）
| 字段 | 类型 |
|---|---|
| `tenant_id` | FK→tenant |
| `item_id` | FK→item |
| `location_id` | FK→location |
| `batch_no` | nvarchar(50) |
| `qty_on_hand` | decimal(18,4) |

---

## 7. 本阶段不建的表（避免过度设计）

以下留到对应 Phase 再按真实需求设计字段，Phase 1 不预先猜测：
- `returnable_asset` 系列（周转资产，Feature Flag 关闭时不需要）
- `integration_connector` / `integration_job` / `integration_log`（集成框架，已降级到 Phase 7）
- 各单据类型的扩展表（`grn_line_ext`、`po_line_ext` 等）
- KPI/报表相关的物化表（先用视图，等报表需求明确再决定是否固化）
