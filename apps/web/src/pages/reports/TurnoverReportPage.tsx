import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Alert, Input, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { TurnoverRow } from "@/api/types";
import { exportReport, presetRange, rangeParams, ReportFilters, TruncatedHint, type Range, type ReportPage } from "@/components/reports";

/** Stock turnover (Ninso TurnOverReport) */
export default function TurnoverReportPage() {
  const [range, setRange] = useState<Range>(presetRange(30));
  const [keyword, setKeyword] = useState("");
  const params = { ...rangeParams(range), keyword: keyword || undefined };
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "turnover", params],
    queryFn: async () => (await apiClient.get<ReportPage<TurnoverRow>>("/reports/turnover", { params })).data,
    placeholderData: (prev) => prev,
  });

  const exportCsv = () => exportReport("/reports/turnover", params);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <ReportFilters range={range} onRangeChange={setRange} onExport={exportCsv} exportDisabled={!data?.total}>
        <Input.Search allowClear placeholder="SKU / item name" style={{ width: 220 }} onSearch={setKeyword} />
      </ReportFilters>
      <Alert
        type="info"
        showIcon
        title="Received includes customer returns, shipped includes returns to supplier; putaways, moves and picks inside the warehouse are excluded. Turnover = shipped in period / average stock (mean of opening and closing); days on hand = days in period / turnover."
      />
      <TruncatedHint page={data} />
      <Table<TurnoverRow>
        rowKey={(r) => r.item.id}
        size="small"
        loading={isFetching && !data}
        style={{ opacity: isFetching && data ? 0.6 : 1 }}
        dataSource={data?.rows}
        scroll={{ x: true }}
        columns={[
          { title: "SKU", render: (_, r) => r.item.sku_code, fixed: "left" },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Unit", render: (_, r) => r.item.base_uom.code },
          { title: "Opening", dataIndex: "opening", align: "right" },
          { title: "Received", dataIndex: "received", align: "right" },
          { title: "Shipped", dataIndex: "shipped", align: "right" },
          { title: "Adjust/count/repack", dataIndex: "other", align: "right" },
          { title: "Closing", dataIndex: "closing", align: "right" },
          { title: "Turnover", dataIndex: "turnover", align: "right", render: (v) => v ?? "-",
            sorter: (a, b) => (a.turnover ?? -1) - (b.turnover ?? -1) },
          { title: "Days on hand", dataIndex: "days_on_hand", align: "right", render: (v) => v ?? "-",
            sorter: (a, b) => (a.days_on_hand ?? Infinity) - (b.days_on_hand ?? Infinity) },
        ]}
      />
    </Space>
  );
}
