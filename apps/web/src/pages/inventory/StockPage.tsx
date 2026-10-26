import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Space, Table, Tabs } from "antd";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { StockBalance, StockLedgerEntry } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { ItemSelect, LocationSelect } from "@/components/selects";
import { MOVEMENT_TYPE_LABELS } from "@/constants/labels";

const DOC_PATHS: Record<string, string> = { GRN: "grns", PUTAWAY: "putaways", PO: "purchase-orders" };

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
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space>
        <ItemSelect allowClear placeholder="按商品筛选" style={{ width: 260 }} value={itemId} onChange={setItemId} />
        <LocationSelect allowClear placeholder="按仓位筛选" style={{ width: 220 }} value={locationId} onChange={setLocationId} />
      </Space>
      <Tabs
        items={[
          {
            key: "balances",
            label: "库存余额",
            children: (
              <Table<StockBalance>
                rowKey="id"
                loading={balances.isLoading}
                dataSource={balances.data}
                columns={[
                  { title: "SKU", render: (_, r) => r.item.sku_code },
                  { title: "商品", render: (_, r) => r.item.name },
                  { title: "仓位", render: (_, r) => r.location.code },
                  { title: "批次号", dataIndex: "batch_no" },
                  { title: "到期日", dataIndex: "expiry_date" },
                  { title: "数量", dataIndex: "qty_on_hand" },
                  { title: "单位", render: (_, r) => r.item.base_uom.code },
                ]}
              />
            ),
          },
          {
            key: "ledger",
            label: "库存流水",
            children: (
              <Table<StockLedgerEntry>
                rowKey="id"
                loading={ledger.isLoading}
                dataSource={ledger.data}
                columns={[
                  { title: "时间", dataIndex: "occurred_at", render: formatDateTime },
                  { title: "类型", dataIndex: "movement_type", render: (v: string) => MOVEMENT_TYPE_LABELS[v] ?? v },
                  { title: "SKU", render: (_, r) => r.item.sku_code },
                  { title: "仓位", render: (_, r) => r.location.code },
                  { title: "批次号", dataIndex: "batch_no" },
                  { title: "变动数量", dataIndex: "qty_change", render: (v: number) => (v > 0 ? `+${v}` : v) },
                  {
                    title: "单据",
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
