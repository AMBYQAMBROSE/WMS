import { useState } from "react";

import { InfoCircleOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Select, Table, Tabs, Typography } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { StockBalance, StockLedgerEntry } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { ItemSelect, LocationSelect } from "@/components/selects";
import { Pill, STICKY_HEADER, Toolbar, formatQty } from "@/components/ui";
import { DOC_PATHS, MOVEMENT_TYPE_LABELS } from "@/constants/labels";

const LIMIT = 500;

const MOVEMENT_TYPE_OPTIONS = Object.entries(MOVEMENT_TYPE_LABELS).map(([value, label]) => ({ value, label }));

/** Expiry state of a balance, from its expiry date only: expired, within 30 days, or nothing to flag */
function ExpiryCell({ date }: { date: string | null }) {
  if (!date) return <span className="wms-empty-value">—</span>;
  const days = dayjs(date).startOf("day").diff(dayjs().startOf("day"), "day");
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}>
      <span className="wms-num">{date}</span>
      {days < 0 ? (
        <Pill tone="red" dot>Expired</Pill>
      ) : days <= 30 ? (
        <Pill tone="amber" dot>{days === 0 ? "Today" : `${days} d`}</Pill>
      ) : null}
    </span>
  );
}

/** Right side of a tab's toolbar: the row count, or a hint when the list hit the server limit */
function ListMeta({ count, noun }: { count: number | undefined; noun: string }) {
  if (count === undefined) return null;
  if (count === LIMIT) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        <InfoCircleOutlined /> Showing the first {LIMIT}; add a filter to narrow down
      </Typography.Text>
    );
  }
  return <span className="wms-toolbar-meta">{count.toLocaleString()} {noun}</span>;
}

const available = (r: StockBalance) => r.qty_on_hand - r.qty_allocated;

function BalancesTab() {
  const [itemId, setItemId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);

  const balances = useQuery({
    queryKey: ["stock", "balances", itemId, locationId, unavailable],
    queryFn: async () =>
      (
        await apiClient.get<StockBalance[]>("/stock/balances", {
          params: { item_id: itemId, location_id: locationId, unavailable: unavailable || undefined, limit: LIMIT },
        })
      ).data,
    placeholderData: (previous) => previous,
  });

  return (
    <>
      <Toolbar
        style={{ marginBottom: 12 }}
        left={
          <>
            <ItemSelect allowClear placeholder="Filter by item" style={{ width: 280 }} value={itemId} onChange={setItemId} aria-label="Filter balances by item" />
            <LocationSelect allowClear placeholder="Filter by location" style={{ width: 220 }} value={locationId} onChange={setLocationId} aria-label="Filter balances by location" />
            <Checkbox checked={unavailable} onChange={(e) => setUnavailable(e.target.checked)}>
              Nothing available only
            </Checkbox>
          </>
        }
        right={<ListMeta count={balances.data?.length} noun="balances" />}
      />
      <Table<StockBalance>
        rowKey="id"
        loading={balances.isLoading}
        className={balances.isFetching && !balances.isLoading ? "wms-refreshing" : undefined}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        dataSource={balances.data}
        rowClassName={(r) => (available(r) <= 0 ? "wms-row-warning" : "")}
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (t) => `${t.toLocaleString()} balances` }}
        columns={[
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Location", render: (_, r) => <span className="wms-mono">{r.location.code}</span> },
          { title: "Batch no.", dataIndex: "batch_no", render: (v: string | null) => v ?? <span className="wms-empty-value">—</span> },
          { title: "Expiry", dataIndex: "expiry_date", render: (v: string | null) => <ExpiryCell date={v} /> },
          { title: "On hand", dataIndex: "qty_on_hand", align: "right", render: formatQty, sorter: (a, b) => a.qty_on_hand - b.qty_on_hand },
          {
            title: "Allocated",
            dataIndex: "qty_allocated",
            align: "right",
            render: (v: number) => (v ? formatQty(v) : <span className="wms-empty-value">—</span>),
          },
          {
            title: "Available",
            key: "available",
            align: "right",
            sorter: (a, b) => available(a) - available(b),
            render: (_, r) => {
              const qty = available(r);
              return (
                <Typography.Text strong type={qty <= 0 ? "warning" : undefined} title={qty <= 0 ? "Fully allocated" : undefined}>
                  {formatQty(qty)}
                </Typography.Text>
              );
            },
          },
          { title: "Unit", render: (_, r) => <Typography.Text type="secondary">{r.item.base_uom.code}</Typography.Text> },
        ]}
      />
    </>
  );
}

function LedgerTab() {
  const [itemId, setItemId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const [movementType, setMovementType] = useState<string>();

  const ledger = useQuery({
    queryKey: ["stock", "ledger", itemId, locationId, movementType],
    queryFn: async () =>
      (
        await apiClient.get<StockLedgerEntry[]>("/stock/ledger", {
          params: { item_id: itemId, location_id: locationId, movement_type: movementType, limit: LIMIT },
        })
      ).data,
    placeholderData: (previous) => previous,
  });

  return (
    <>
      <Toolbar
        style={{ marginBottom: 12 }}
        left={
          <>
            <ItemSelect allowClear placeholder="Filter by item" style={{ width: 280 }} value={itemId} onChange={setItemId} aria-label="Filter movements by item" />
            <LocationSelect allowClear placeholder="Filter by location" style={{ width: 220 }} value={locationId} onChange={setLocationId} aria-label="Filter movements by location" />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Movement type"
              style={{ width: 200 }}
              options={MOVEMENT_TYPE_OPTIONS}
              value={movementType}
              onChange={setMovementType}
              aria-label="Filter movements by type"
            />
          </>
        }
        right={<ListMeta count={ledger.data?.length} noun="movements" />}
      />
      <Table<StockLedgerEntry>
        rowKey="id"
        loading={ledger.isLoading}
        className={ledger.isFetching && !ledger.isLoading ? "wms-refreshing" : undefined}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        dataSource={ledger.data}
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (t) => `${t.toLocaleString()} movements` }}
        columns={[
          { title: "Time", dataIndex: "occurred_at", render: (v: string) => <span style={{ whiteSpace: "nowrap" }}>{formatDateTime(v)}</span> },
          { title: "Type", dataIndex: "movement_type", render: (v: string) => MOVEMENT_TYPE_LABELS[v] ?? v },
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
          { title: "Location", render: (_, r) => <span className="wms-mono">{r.location.code}</span> },
          { title: "Batch no.", dataIndex: "batch_no", render: (v: string | null) => v ?? <span className="wms-empty-value">—</span> },
          {
            title: "Change",
            dataIndex: "qty_change",
            align: "right",
            render: (v: number) => (
              <Typography.Text strong type={v < 0 ? "danger" : "success"}>
                {v > 0 ? `+${formatQty(v)}` : formatQty(v)}
              </Typography.Text>
            ),
          },
          {
            title: "Document",
            render: (_, r) => {
              const doc = r.ref_line?.document;
              return doc && <Link className="wms-mono" to={`/${DOC_PATHS[doc.doc_type]}/${doc.id}`}>{doc.doc_no}</Link>;
            },
          },
        ]}
      />
    </>
  );
}

export default function StockPage() {
  return (
    <Tabs
      items={[
        { key: "balances", label: "Balances", children: <BalancesTab /> },
        { key: "ledger", label: "Movement history", children: <LedgerTab /> },
      ]}
    />
  );
}
