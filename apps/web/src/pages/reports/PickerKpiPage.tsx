import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { PickerKpiRow } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { exportReport, presetRange, rangeParams, ReportFilters, TruncatedHint, type Range, type ReportPage } from "@/components/reports";

/** Picker performance (Ninso PickerIndiKPI): by the user who confirmed the picks */
export default function PickerKpiPage() {
  const [range, setRange] = useState<Range>(presetRange(7));
  const params = rangeParams(range);
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "picker-kpi", params],
    queryFn: async () => (await apiClient.get<ReportPage<PickerKpiRow>>("/reports/picker-kpi", { params })).data,
    placeholderData: (prev) => prev,
  });

  const exportCsv = () => exportReport("/reports/picker-kpi", params);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <ReportFilters range={range} onRangeChange={setRange} onExport={exportCsv} exportDisabled={!data?.total} />
      <TruncatedHint page={data} />
      <Table<PickerKpiRow>
        rowKey="user_id"
        size="small"
        loading={isFetching && !data}
        style={{ opacity: isFetching && data ? 0.6 : 1 }}
        dataSource={data?.rows}
        columns={[
          { title: "Picker", render: (_, r) => `${r.display_name} (${r.username})` },
          { title: "Pick lists", dataIndex: "picks", align: "right", sorter: (a, b) => a.picks - b.picks },
          { title: "Lines", dataIndex: "lines", align: "right", sorter: (a, b) => a.lines - b.lines, defaultSortOrder: "descend" },
          { title: "Quantity", dataIndex: "qty", align: "right", sorter: (a, b) => a.qty - b.qty },
          { title: "Short lines", dataIndex: "short_lines", align: "right" },
          { title: "Fill rate", dataIndex: "fill_rate", align: "right", render: (v: number | null) => (v === null ? "-" : `${v}%`) },
          { title: "First confirm", dataIndex: "first_at", render: formatDateTime },
          { title: "Last confirm", dataIndex: "last_at", render: formatDateTime },
        ]}
      />
    </Space>
  );
}
