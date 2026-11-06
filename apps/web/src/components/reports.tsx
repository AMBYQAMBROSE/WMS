import type { ReactNode } from "react";

import { DownloadOutlined } from "@ant-design/icons";
import { Alert, Button, DatePicker, Segmented } from "antd";
import dayjs, { type Dayjs } from "dayjs";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { Toolbar } from "@/components/ui";

export type Range = [Dayjs, Dayjs];

const PRESETS: { key: string; label: string; days: number }[] = [
  { key: "today", label: "Today", days: 1 },
  { key: "7", label: "Last 7 days", days: 7 },
  { key: "30", label: "Last 30 days", days: 30 },
  { key: "90", label: "Last 90 days", days: 90 },
];

export const presetRange = (days: number): Range => [dayjs().subtract(days - 1, "day").startOf("day"), dayjs().startOf("day")];

export const rangeParams = ([from, to]: Range) => ({
  date_from: from.format("YYYY-MM-DD"),
  date_to: to.format("YYYY-MM-DD"),
});

/** Report filters: date range first, presets before a custom range; all filters in one row */
export function ReportFilters({
  range,
  onRangeChange,
  children,
  onExport,
  exportDisabled,
}: {
  range?: Range;
  onRangeChange?: (range: Range) => void;
  children?: ReactNode;
  onExport?: () => void;
  exportDisabled?: boolean;
}) {
  const preset = range && PRESETS.find((p) => range[1].isSame(dayjs(), "day") && range[1].diff(range[0], "day") + 1 === p.days);
  return (
    <Toolbar
      left={
        <>
        {range && onRangeChange && (
          <>
            <Segmented
              value={preset?.key ?? "custom"}
              onChange={(key) => {
                const p = PRESETS.find((x) => x.key === key);
                if (p) onRangeChange(presetRange(p.days));
              }}
              options={[...PRESETS.map((p) => ({ value: p.key, label: p.label })), { value: "custom", label: "Custom", disabled: true }]}
            />
            <DatePicker.RangePicker
              allowClear={false}
              value={range}
              disabledDate={(d) => d.isAfter(dayjs(), "day")}
              onChange={(v) => v?.[0] && v[1] && onRangeChange([v[0], v[1]])}
              data-testid="report-range"
            />
          </>
        )}
        {children}
        </>
      }
      right={
        onExport && (
          <Button icon={<DownloadOutlined />} onClick={onExport} disabled={exportDisabled}>
            Export CSV
          </Button>
        )
      }
    />
  );
}

/** Paged report response: rows holds only the first `limit` rows, total is the full row count */
export interface ReportPage<T> {
  total: number;
  rows: T[];
}

/** When only the first N rows are shown, point to the full export */
export function TruncatedHint({ page }: { page?: ReportPage<unknown> }) {
  if (!page || page.total <= page.rows.length) return null;
  return (
    <Alert
      type="warning"
      showIcon
      title={`${page.total.toLocaleString()} rows; showing the first ${page.rows.length.toLocaleString()}. Export CSV for the full data or narrow the filters.`}
    />
  );
}

/** Export: the server builds the full CSV (UTF-8 with BOM so Excel opens it correctly) */
export async function exportReport(path: string, params: Record<string, unknown>) {
  try {
    const res = await apiClient.get<Blob>(path, { params: { ...params, format: "csv" }, responseType: "blob" });
    const disposition = String(res.headers["content-disposition"] ?? "");
    const match = /filename\*=UTF-8''([^;]+)/.exec(disposition);
    const filename = match ? decodeURIComponent(match[1]) : "report.csv";
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    showError(error);
  }
}
