import { useEffect, useMemo, useState } from "react";

import { DeleteOutlined, PlusOutlined, RedoOutlined, SearchOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Typography,
  message,
} from "antd";
import type { Dayjs } from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan, useMe } from "@/api/me";
import { usePreference } from "@/api/preferences";
import type { CatalogItem, CatalogPage, DocumentSummary, PartnerBrief, SalesOrder } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { formatDateTime } from "@/components/documents";
import { Pill, Toolbar, formatQty } from "@/components/ui";

const PAGE_SIZE = 48;
// The cart is saved in the user's preferences (32 KB limit): plenty for a normal order
const MAX_LINES = 100;

/** One cart line. Names are kept so the cart shows without refetching; factor/available drive the stock hint. */
interface CartLine {
  item_id: string;
  sku_code: string;
  name: string;
  uom_id: string;
  uom_code: string;
  /** Base units per one of this unit; null when unknown (line copied from an old order) */
  factor: number | null;
  /** Available stock in base units when the line was added */
  available: number | null;
  qty: number;
}

interface Cart {
  lines: CartLine[];
  /** Staff only: the customer chosen for this order */
  partner?: PartnerBrief | null;
}

const EMPTY_CART: Cart = { lines: [] };

function useDebounced<T>(value: T, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function StockPill({ available, uom }: { available: number; uom: string }) {
  if (available <= 0) return <Pill tone="slate" dot>Out of stock</Pill>;
  return (
    <Pill tone="green" dot>
      {formatQty(available)} {uom}
    </Pill>
  );
}

/** A catalog row: choose unit and quantity, then add */
function AddToCart({ item, inCart, onAdd }: { item: CatalogItem; inCart: number; onAdd: (uomId: string, qty: number) => void }) {
  const [uomId, setUomId] = useState(item.base_uom.id);
  const [qty, setQty] = useState<number | null>(1);
  const add = () => {
    if (qty && qty > 0) onAdd(uomId, qty);
  };
  return (
    <Space.Compact>
      <InputNumber
        min={0.0001}
        value={qty}
        onChange={setQty}
        onPressEnter={add}
        style={{ width: 84 }}
        aria-label={`Quantity of ${item.sku_code}`}
      />
      {item.uoms.length > 1 ? (
        <Select
          value={uomId}
          onChange={setUomId}
          style={{ width: 92 }}
          options={item.uoms.map((u) => ({ value: u.id, label: u.code, title: u.factor === 1 ? u.name : `${u.name} = ${formatQty(u.factor)} ${item.base_uom.code}` }))}
          aria-label={`Unit of ${item.sku_code}`}
        />
      ) : (
        <Button disabled style={{ width: 64, cursor: "default" }}>
          {item.base_uom.code}
        </Button>
      )}
      <Badge count={inCart} size="small" offset={[-4, 2]}>
        <Button type="primary" icon={<PlusOutlined />} onClick={add} disabled={!qty || qty <= 0} aria-label={`Add ${item.sku_code} to cart`}>
          Add
        </Button>
      </Badge>
    </Space.Compact>
  );
}

function Catalog({ cart, onAdd }: { cart: Cart; onAdd: (item: CatalogItem, uomId: string, qty: number) => void }) {
  const [typed, setTyped] = useState("");
  const keyword = useDebounced(typed.trim());
  const [category, setCategory] = useState<string>();
  const [inStockOnly, setInStockOnly] = useState(false);
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [keyword, category, inStockOnly]);

  const { data, isFetching } = useQuery({
    queryKey: ["cart", "catalog", keyword, category, inStockOnly, page],
    queryFn: async () =>
      (
        await apiClient.get<CatalogPage>("/cart/catalog", {
          params: { keyword: keyword || undefined, category, in_stock_only: inStockOnly, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE },
        })
      ).data,
    placeholderData: (previous) => previous,
  });

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    cart.lines.forEach((l) => m.set(l.item_id, (m.get(l.item_id) ?? 0) + 1));
    return m;
  }, [cart.lines]);

  // A scanned barcode (or an exact SKU) with Enter adds one of that item straight away
  const quickAdd = () => {
    const needle = typed.trim().toLowerCase();
    const hit = data?.items.find((i) => i.sku_code.toLowerCase() === needle || i.barcode?.toLowerCase() === needle);
    if (hit && keyword === typed.trim()) {
      onAdd(hit, hit.base_uom.id, 1);
      setTyped("");
    }
  };

  return (
    <Card size="small" title="Items">
      <Toolbar
        style={{ marginBottom: 12 }}
        left={
          <>
            <Input
              allowClear
              autoFocus
              prefix={<SearchOutlined style={{ color: "var(--ant-color-text-quaternary)" }} />}
              placeholder="Search SKU, name, or scan a barcode"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onPressEnter={quickAdd}
              style={{ width: 280 }}
              aria-label="Search items"
            />
            <Select
              allowClear
              placeholder="All categories"
              value={category}
              onChange={setCategory}
              style={{ width: 180 }}
              options={(data?.categories ?? []).map((c) => ({ value: c, label: c }))}
              aria-label="Category"
            />
          </>
        }
        right={
          <Space size={6}>
            <Switch size="small" checked={inStockOnly} onChange={setInStockOnly} id="cart-in-stock" />
            <label htmlFor="cart-in-stock">In stock only</label>
          </Space>
        }
      />
      <Table<CatalogItem>
        size="small"
        rowKey="id"
        loading={isFetching}
        dataSource={data?.items}
        scroll={{ x: "max-content" }}
        pagination={{ current: page, pageSize: PAGE_SIZE, total: data?.total ?? 0, onChange: setPage, showSizeChanger: false, hideOnSinglePage: true }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No matching items" /> }}
        columns={[
          { title: "SKU", dataIndex: "sku_code", render: (v: string) => <span className="wms-mono">{v}</span> },
          { title: "Item", dataIndex: "name" },
          { title: "Category", dataIndex: "category", responsive: ["lg"], render: (v: string | null) => v || <span className="wms-empty-value">—</span> },
          { title: "Available", dataIndex: "available", render: (v: number, i) => <StockPill available={v} uom={i.base_uom.code} /> },
          {
            title: "",
            key: "add",
            align: "right",
            render: (_, item) => <AddToCart item={item} inCart={counts.get(item.id) ?? 0} onAdd={(uomId, qty) => onAdd(item, uomId, qty)} />,
          },
        ]}
      />
    </Card>
  );
}

function CustomerPicker({ value, onChange }: { value?: PartnerBrief | null; onChange: (p: PartnerBrief | null) => void }) {
  const [typed, setTyped] = useState("");
  const keyword = useDebounced(typed.trim());
  const { data, isFetching } = useQuery({
    queryKey: ["cart", "customers", keyword],
    queryFn: async () => (await apiClient.get<PartnerBrief[]>("/cart/customers", { params: { keyword: keyword || undefined } })).data,
  });
  const options = [...(data ?? []), ...(value && !data?.some((p) => p.id === value.id) ? [value] : [])];
  return (
    <Select
      showSearch
      allowClear
      filterOption={false}
      onSearch={setTyped}
      loading={isFetching}
      placeholder="Search customer code or name"
      value={value?.id}
      onChange={(id) => onChange(options.find((p) => p.id === id) ?? null)}
      options={options.map((p) => ({ value: p.id, label: `${p.code} ${p.name}` }))}
      style={{ width: "100%" }}
      aria-label="Customer"
    />
  );
}

function CartPanel({
  cart,
  fixedPartner,
  onChange,
  onSubmitted,
}: {
  cart: Cart;
  fixedPartner: PartnerBrief | null | undefined;
  onChange: (cart: Cart) => void;
  onSubmitted: (order: SalesOrder) => void;
}) {
  const [date, setDate] = useState<Dayjs | null>(null);
  const [remark, setRemark] = useState("");
  const partner = fixedPartner ?? cart.partner;

  const setLine = (index: number, patch: Partial<CartLine> | null) =>
    onChange({ ...cart, lines: patch === null ? cart.lines.filter((_, i) => i !== index) : cart.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)) });

  const submit = useMutation({
    mutationFn: async () =>
      (
        await apiClient.post<SalesOrder>(
          "/cart/orders",
          {
            partner_id: fixedPartner ? null : partner?.id,
            expected_date: date ? date.format("YYYY-MM-DD") : null,
            remark: remark.trim() || null,
            lines: cart.lines.map((l) => ({ item_id: l.item_id, uom_id: l.uom_id, qty: l.qty })),
          },
          // A retried click (slow network) must not place the order twice
          { headers: { "Idempotency-Key": crypto.randomUUID() } },
        )
      ).data,
    onSuccess: (order) => {
      setDate(null);
      setRemark("");
      onSubmitted(order);
    },
    onError: showError,
  });

  const short = cart.lines.filter((l) => l.factor !== null && l.available !== null && l.qty * l.factor > l.available);

  return (
    <Card
      size="small"
      title={
        <Space>
          <ShoppingCartOutlined />
          Cart
          {cart.lines.length > 0 && <Typography.Text type="secondary">({cart.lines.length} {cart.lines.length === 1 ? "line" : "lines"})</Typography.Text>}
        </Space>
      }
      extra={
        cart.lines.length > 0 && (
          <Popconfirm title="Empty the cart?" onConfirm={() => onChange({ ...cart, lines: [] })}>
            <Button size="small" type="text" danger>
              Empty
            </Button>
          </Popconfirm>
        )
      }
      style={{ position: "sticky", top: 72 }}
    >
      <Space orientation="vertical" style={{ width: "100%" }} size="middle">
        <div>
          <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
            Order for
          </Typography.Text>
          {fixedPartner ? (
            <div style={{ fontWeight: 500 }}>
              {fixedPartner.code} {fixedPartner.name}
            </div>
          ) : (
            <CustomerPicker value={cart.partner} onChange={(p) => onChange({ ...cart, partner: p })} />
          )}
        </div>

        {cart.lines.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Add items from the list" />
        ) : (
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            {cart.lines.map((l, i) => (
              <div
                key={`${l.item_id}-${l.uom_id}`}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--ant-color-split)" }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.name}>
                    {l.name}
                  </div>
                  <Typography.Text type="secondary" className="wms-mono" style={{ fontSize: 12 }}>
                    {l.sku_code}
                  </Typography.Text>
                </div>
                <InputNumber
                  size="small"
                  min={0.0001}
                  value={l.qty}
                  onChange={(v) => v && v > 0 && setLine(i, { qty: v })}
                  style={{ width: 76 }}
                  aria-label={`Quantity of ${l.sku_code} in cart`}
                />
                <span style={{ width: 36, fontSize: 12.5 }}>{l.uom_code}</span>
                <Button size="small" type="text" icon={<DeleteOutlined />} onClick={() => setLine(i, null)} aria-label={`Remove ${l.sku_code}`} />
              </div>
            ))}
          </div>
        )}

        {short.length > 0 && (
          <Alert
            type="warning"
            showIcon
            title={`${short.length === 1 ? "1 line is" : `${short.length} lines are`} more than the stock available now`}
            description="You can still order: the warehouse ships what is available and the rest when it arrives."
          />
        )}

        <DatePicker
          value={date}
          onChange={setDate}
          placeholder="Requested ship date (optional)"
          style={{ width: "100%" }}
          disabledDate={(d) => d.isBefore(new Date(), "day")}
        />
        <Input.TextArea value={remark} onChange={(e) => setRemark(e.target.value)} maxLength={400} autoSize={{ minRows: 2, maxRows: 4 }} placeholder="Remark for the warehouse (optional)" />
        <Button
          type="primary"
          block
          size="large"
          disabled={cart.lines.length === 0 || !partner}
          loading={submit.isPending}
          onClick={() => submit.mutate()}
        >
          {partner ? "Place order" : "Choose a customer to order"}
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
          The order goes to the warehouse as a draft; you can withdraw it until they confirm it.
        </Typography.Text>
      </Space>
    </Card>
  );
}

function OrderLines({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["cart", "order", id],
    queryFn: async () => (await apiClient.get<SalesOrder>(`/cart/orders/${id}`)).data,
  });
  return (
    <Table
      size="small"
      rowKey="id"
      loading={isLoading}
      dataSource={data?.lines}
      pagination={false}
      columns={[
        { title: "SKU", render: (_, l) => <span className="wms-mono">{l.item.sku_code}</span> },
        { title: "Item", render: (_, l) => l.item.name },
        { title: "Ordered", align: "right", render: (_, l) => `${formatQty(l.qty_planned)} ${l.uom.code}` },
        { title: "Shipped", align: "right", render: (_, l) => `${formatQty(l.shipped)} ${l.item.base_uom.code}` },
      ]}
    />
  );
}

function MyOrders({ onReorder }: { onReorder: (order: SalesOrder) => void }) {
  const can = useCan();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string>();
  const { data, isFetching } = useQuery({
    queryKey: ["cart", "orders", status],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/cart/orders", { params: { status, limit: 100 } })).data,
  });
  const cancel = useMutation({
    mutationFn: async (id: string) => (await apiClient.post(`/cart/orders/${id}/cancel`)).data,
    onSuccess: () => {
      message.success("Order withdrawn");
      queryClient.invalidateQueries({ queryKey: ["cart", "orders"] });
      queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
    },
    onError: showError,
  });
  const reorder = useMutation({
    mutationFn: async (id: string) => (await apiClient.get<SalesOrder>(`/cart/orders/${id}`)).data,
    onSuccess: onReorder,
    onError: showError,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <>
            {[undefined, "DRAFT", "CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED", "SHIPPED", "CANCELLED"].map((s) => (
              <button type="button" key={s ?? "all"} className={`wms-chip${status === s ? " wms-chip-active" : ""}`} onClick={() => setStatus(s)}>
                {s ? <StatusTag status={s} /> : "All"}
              </button>
            ))}
          </>
        }
      />
      <Table<DocumentSummary>
        size="small"
        rowKey="id"
        loading={isFetching}
        dataSource={data}
        scroll={{ x: "max-content" }}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        expandable={{ expandedRowRender: (r) => <OrderLines id={r.id} /> }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No orders yet" /> }}
        columns={[
          {
            title: "Order no.",
            dataIndex: "doc_no",
            render: (v: string, r) => (can("sales_order.read") ? <Link className="wms-mono" to={`/sales-orders/${r.id}`}>{v}</Link> : <span className="wms-mono">{v}</span>),
          },
          { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
          { title: "Customer", render: (_, r) => r.partner?.name },
          { title: "Requested ship date", dataIndex: "expected_date", render: (v: string | null) => v || <span className="wms-empty-value">—</span> },
          { title: "Remark", dataIndex: "remark", ellipsis: true },
          { title: "Ordered", dataIndex: "created_at", render: (v: string | null) => formatDateTime(v) },
          {
            title: "",
            key: "actions",
            align: "right",
            render: (_, r) => (
              <Space size={4}>
                <Button size="small" type="text" icon={<RedoOutlined />} loading={reorder.isPending && reorder.variables === r.id} onClick={() => reorder.mutate(r.id)}>
                  Order again
                </Button>
                {r.status === "DRAFT" && (
                  <Popconfirm title="Withdraw this order?" okText="Withdraw" okButtonProps={{ danger: true }} onConfirm={() => cancel.mutate(r.id)}>
                    <Button size="small" type="text" danger>
                      Withdraw
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}

/** Shopping cart: browse items, collect them in a cart, place a draft sales order. Customer accounts order only for their own customer. */
export default function CartPage() {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const stored = usePreference<Cart>("cart", EMPTY_CART);
  const [tab, setTab] = useState("order");
  const cart = stored.value;
  const fixedPartner = me?.partner;

  const save = (next: Cart) => {
    if (!stored.loaded) return;
    stored.save(next);
  };

  const addLine = (line: CartLine) => {
    const lines = [...cart.lines];
    const existing = lines.findIndex((l) => l.item_id === line.item_id && l.uom_id === line.uom_id);
    if (existing >= 0) {
      lines[existing] = { ...lines[existing]!, qty: lines[existing]!.qty + line.qty, available: line.available ?? lines[existing]!.available };
    } else if (lines.length >= MAX_LINES) {
      message.warning(`A cart holds at most ${MAX_LINES} lines; place this order first`);
      return false;
    } else {
      lines.push(line);
    }
    save({ ...cart, lines });
    return true;
  };

  const addItem = (item: CatalogItem, uomId: string, qty: number) => {
    const uom = item.uoms.find((u) => u.id === uomId) ?? { ...item.base_uom, factor: 1 };
    const added = addLine({
      item_id: item.id, sku_code: item.sku_code, name: item.name, uom_id: uom.id, uom_code: uom.code,
      factor: uom.factor, available: item.available, qty,
    });
    if (added) message.success({ content: `Added ${formatQty(qty)} ${uom.code} ${item.sku_code}`, key: "cart-add", duration: 1.5 });
  };

  const reorder = (order: SalesOrder) => {
    if (!stored.loaded) return;
    const lines = [...cart.lines];
    for (const l of order.lines) {
      const i = lines.findIndex((c) => c.item_id === l.item.id && c.uom_id === l.uom.id);
      if (i >= 0) lines[i] = { ...lines[i]!, qty: lines[i]!.qty + l.qty_planned };
      else
        lines.push({
          item_id: l.item.id, sku_code: l.item.sku_code, name: l.item.name, uom_id: l.uom.id, uom_code: l.uom.code,
          factor: l.uom.id === l.item.base_uom.id ? 1 : null, available: null, qty: l.qty_planned,
        });
    }
    if (lines.length > MAX_LINES) {
      message.warning(`A cart holds at most ${MAX_LINES} lines`);
      return;
    }
    save({ lines, partner: fixedPartner ? null : (cart.partner ?? order.partner) });
    setTab("order");
    message.success(`Added the lines of ${order.doc_no} to the cart`);
  };

  const submitted = (order: SalesOrder) => {
    save({ ...cart, lines: [] });
    queryClient.invalidateQueries({ queryKey: ["cart", "orders"] });
    queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
    message.success(`Order ${order.doc_no} placed. The warehouse will confirm it.`);
    setTab("orders");
  };

  return (
    <Tabs
      activeKey={tab}
      onChange={setTab}
      items={[
        {
          key: "order",
          label: (
            <Badge count={cart.lines.length} size="small" offset={[8, 0]}>
              Order
            </Badge>
          ),
          children: (
            <Row gutter={[16, 16]} align="top">
              <Col xs={24} xl={16}>
                <Catalog cart={cart} onAdd={addItem} />
              </Col>
              <Col xs={24} xl={8}>
                <CartPanel cart={cart} fixedPartner={fixedPartner} onChange={save} onSubmitted={submitted} />
              </Col>
            </Row>
          ),
        },
        { key: "orders", label: "My orders", children: <MyOrders onReorder={reorder} /> },
      ]}
    />
  );
}
