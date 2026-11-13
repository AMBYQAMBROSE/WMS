import { useState } from "react";

import { InfoCircleOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Space, Table, Tabs, Typography } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { StockBalance, StockLedgerEntry } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { ItemSelect, LocationSelect } from "@/components/selects";
import { Pill, STICKY_HEADER, Toolbar, formatQty } from "@/components/ui";
import { DOC_PATHS, MOVEMENT_TYPE_LABELS } from "@/constants/labels";

const LIMIT = 500;

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

export default function StockPage() {
  const [itemId, setItemId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const params = { item_id: itemId, location_id: locationId, limit: LIMIT };

  const balances = useQuery({
    queryKey: ["stock", "balances", itemId, locationId],
    queryFn: async () => (await apiClient.get<StockBalance[]>("/stock/balances", { params })).data,
    placeholderData: (previous) => previous,
  });
  const ledger = useQuery({
    queryKey: ["stock", "ledger", itemId, locationId],
    queryFn: async () => (await apiClient.get<StockLedgerEntry[]>("/stock/ledger", { params })).data,
    placeholderData: (previous) => previous,
  });

  const limited = balances.data?.length === LIMIT || ledger.data?.length === LIMIT;

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <>
            <ItemSelect allowClear placeholder="Filter by item" style={{ width: 280 }} value={itemId} onChange={setItemId} aria-label="Filter by item" />
            <LocationSelect allowClear placeholder="Filter by location" style={{ width: 220 }} value={locationId} onChange={setLocationId} aria-label="Filter by location" />
          </>
        }
        right={
          limited ? (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              <InfoCircleOutlined /> Showing the first {LIMIT}; filter by item or location to narrow down
            </Typography.Text>
          ) : balances.data ? (
            <span className="wms-toolbar-meta">{balances.data.length.toLocaleString()} balances</span>
          ) : null
        }
      />
      <Tabs
        items={[
          {
            key: "balances",
            label: "Balances",
            children: (
              <Table<StockBalance>
                rowKey="id"
                loading={balances.isLoading}
                className={balances.isFetching && !balances.isLoading ? "wms-refreshing" : undefined}
                sticky={STICKY_HEADER}
                scroll={{ x: "max-content" }}
                dataSource={balances.data}
                rowClassName={(r) => (r.qty_on_hand - r.qty_allocated <= 0 ? "wms-row-warning" : "")}
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
                    sorter: (a, b) => a.qty_on_hand - a.qty_allocated - (b.qty_on_hand - b.qty_allocated),
                    render: (_, r) => {
                      const available = r.qty_on_hand - r.qty_allocated;
                      return (
                        <Typography.Text strong type={available <= 0 ? "warning" : undefined} title={available <= 0 ? "Fully allocated" : undefined}>
                          {formatQty(available)}
                        </Typography.Text>
                      );
                    },
                  },
                  { title: "Unit", render: (_, r) => <Typography.Text type="secondary">{r.item.base_uom.code}</Typography.Text> },
                ]}
              />
            ),
          },
          {
            key: "ledger",
            label: "Movement history",
            children: (
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
            ),
          },
        ]}
      />
    </Space>
  );
}
