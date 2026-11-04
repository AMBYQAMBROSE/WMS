import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Space, Table, Tabs } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { StockBalance, StockLedgerEntry } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { ItemSelect, LocationSelect } from "@/components/selects";
import { DOC_PATHS, MOVEMENT_TYPE_LABELS } from "@/constants/labels";

export default function StockPage() {
  const [itemId, setItemId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const params = { item_id: itemId, location_id: locationId, limit: 500 };

  const balances = useQuery({
    queryKey: ["stock", "balances", itemId, locationId],
    queryFn: async () => (await apiClient.get<StockBalance[]>("/stock/balances", { params })).data,
  });
  const ledger = useQuery({
    queryKey: ["stock", "ledger", itemId, locationId],
    queryFn: async () => (await apiClient.get<StockLedgerEntry[]>("/stock/ledger", { params })).data,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Space>
        <ItemSelect allowClear placeholder="Filter by item" style={{ width: 260 }} value={itemId} onChange={setItemId} />
        <LocationSelect allowClear placeholder="Filter by location" style={{ width: 220 }} value={locationId} onChange={setLocationId} />
      </Space>
      <Tabs
        items={[
          {
            key: "balances",
            label: "Balances",
            children: (
              <Table<StockBalance>
                rowKey="id"
                loading={balances.isLoading}
                dataSource={balances.data}
                columns={[
                  { title: "SKU", render: (_, r) => r.item.sku_code },
                  { title: "Item", render: (_, r) => r.item.name },
                  { title: "Location", render: (_, r) => r.location.code },
                  { title: "Batch no.", dataIndex: "batch_no" },
                  { title: "Expiry date", dataIndex: "expiry_date" },
                  { title: "On hand", dataIndex: "qty_on_hand" },
                  { title: "Allocated", dataIndex: "qty_allocated", render: (v: number) => (v ? v : "") },
                  { title: "Available", render: (_, r) => r.qty_on_hand - r.qty_allocated },
                  { title: "Unit", render: (_, r) => r.item.base_uom.code },
                ]}
              />
            ),
          },
          {
            key: "ledger",
            label: "Ledger",
            children: (
              <Table<StockLedgerEntry>
                rowKey="id"
                loading={ledger.isLoading}
                dataSource={ledger.data}
                columns={[
                  { title: "Time", dataIndex: "occurred_at", render: formatDateTime },
                  { title: "Type", dataIndex: "movement_type", render: (v: string) => MOVEMENT_TYPE_LABELS[v] ?? v },
                  { title: "SKU", render: (_, r) => r.item.sku_code },
                  { title: "Location", render: (_, r) => r.location.code },
                  { title: "Batch no.", dataIndex: "batch_no" },
                  { title: "Change", dataIndex: "qty_change", render: (v: number) => (v > 0 ? `+${v}` : v) },
                  {
                    title: "Document",
                    render: (_, r) => {
                      const doc = r.ref_line?.document;
                      return doc && <Link to={`/${DOC_PATHS[doc.doc_type]}/${doc.id}`}>{doc.doc_no}</Link>;
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
