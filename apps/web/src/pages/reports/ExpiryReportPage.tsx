import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Segmented, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { ExpiryRow } from "@/api/types";
import { Pill, STICKY_HEADER, formatQty } from "@/components/ui";
import { exportReport, ReportFilters, TruncatedHint, type ReportPage } from "@/components/reports";

const WINDOWS = [7, 30, 60, 90, 180];

/** Expiring stock: expired batches plus those expiring within the chosen number of days */
export default function ExpiryReportPage() {
  const [within, setWithin] = useState(30);
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "expiry", within],
    queryFn: async () => (await apiClient.get<ReportPage<ExpiryRow>>("/reports/expiry", { params: { within_days: within } })).data,
    placeholderData: (prev) => prev,
  });

  const exportCsv = () => exportReport("/reports/expiry", { within_days: within });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <ReportFilters onExport={exportCsv} exportDisabled={!data?.total}>
        <Segmented
          value={within}
          onChange={(v) => setWithin(Number(v))}
          options={WINDOWS.map((d) => ({ value: d, label: `Within ${d} days` }))}
        />
      </ReportFilters>
      <TruncatedHint page={data} />
      <Table<ExpiryRow>
        rowKey={(r) => `${r.item.id}-${r.location_code}-${r.batch_no}-${r.expiry_date}`}
        size="small"
        loading={isFetching && !data}
        className={isFetching && data ? "wms-refreshing" : undefined}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        dataSource={data?.rows}
        columns={[
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Location", dataIndex: "location_code", render: (v: string) => <span className="wms-mono">{v}</span> },
          { title: "Batch", dataIndex: "batch_no" },
          { title: "Expiry date", dataIndex: "expiry_date" },
          {
            title: "Remaining",
            dataIndex: "days_left",
            align: "right",
            // Status uses text plus color, never color alone
            render: (v: number) =>
              v < 0 ? (
                <Pill tone="red" dot>Expired {-v} days ago</Pill>
              ) : v <= 7 ? (
                <Pill tone="amber" dot>{v} days</Pill>
              ) : (
                `${v} days`
              ),
          },
          { title: "On hand", dataIndex: "qty_on_hand", align: "right", render: formatQty },
          { title: "Allocated", dataIndex: "qty_allocated", align: "right", render: formatQty },
          { title: "Unit", render: (_, r) => r.item.base_uom.code },
        ]}
      />
    </Space>
  );
}
