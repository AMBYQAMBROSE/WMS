import { useMemo, useState } from "react";

import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { Card, Col, Row, Segmented, Table, Tooltip, Typography } from "antd";
import dayjs from "dayjs";

import { useCan, useFeature } from "@/api/me";
import { usePreference } from "@/api/preferences";
import type { Analytics, ItemTrendRow, MonthPoint } from "@/api/types";
import TrendChart from "@/components/TrendChart";
import { emptyLocale, formatMoney, formatPct } from "@/components/ui";
import { useUiStore } from "@/stores/uiStore";

type Metric = "purchases" | "losses";
type Measure = "qty" | "value";
type Unit = "base" | "packing";

// Categorical slots 1-3 of the reference palette, validated all-pairs for color vision deficiency in both modes.
// The 3-year average is also dashed, so it never relies on color alone (slot 3 is below 3:1 on the light surface)
const YOY_SERIES = {
  light: [
    { key: "this_year", name: "This year", color: "#2a78d6" },
    { key: "last_year", name: "Last year", color: "#eb6834" },
    { key: "avg_3y", name: "3-year average", color: "#1baf7a", dashed: true },
  ],
  dark: [
    { key: "this_year", name: "This year", color: "#3987e5" },
    { key: "last_year", name: "Last year", color: "#d95926" },
    { key: "avg_3y", name: "3-year average", color: "#199e70", dashed: true },
  ],
};

const METRIC_FIELDS: Record<Metric, { qty: keyof MonthPoint; value: keyof MonthPoint; label: string }> = {
  purchases: { qty: "purchased_qty", value: "purchased_value", label: "Stock purchases" },
  losses: { qty: "loss_qty", value: "loss_value", label: "Stock loss" },
};

const pct = (now: number, before: number) => (before ? ((now - before) / before) * 100 : null);
const fmtQty = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 });

/** Change against a comparison period, with an arrow and words (an increase in losses is bad, in purchases neutral) */
function Delta({ now, before, badWhenUp = false }: { now: number; before: number; badWhenUp?: boolean }) {
  const change = pct(now, before);
  if (change === null) return <Typography.Text type="secondary" style={{ fontSize: 12 }}>no comparison</Typography.Text>;
  const up = change > 0;
  const color = change === 0 ? undefined : badWhenUp === up ? "var(--wms-tone-red-fg)" : badWhenUp ? "var(--wms-tone-green-fg)" : undefined;
  return (
    <span style={{ fontSize: 12.5, color, whiteSpace: "nowrap" }} className="wms-num">
      {change !== 0 && (up ? <ArrowUpOutlined aria-hidden /> : <ArrowDownOutlined aria-hidden />)} {formatPct(change)}
    </span>
  );
}

function PeriodTile({ label, hint, value, compare, compareLabel, format, badWhenUp }: {
  label: string;
  hint: string;
  value: number;
  compare?: number;
  compareLabel?: string;
  format: (v: number) => string;
  badWhenUp?: boolean;
}) {
  return (
    <div className="wms-period-tile">
      <Tooltip title={hint}>
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>{label}</Typography.Text>
      </Tooltip>
      <div className="wms-num" style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.5, lineHeight: 1.3 }}>{format(value)}</div>
      {compare !== undefined && (
        <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
          <Delta now={value} before={compare} badWhenUp={badWhenUp} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {compareLabel} {format(compare)}
          </Typography.Text>
        </div>
      )}
    </div>
  );
}

/** Trend analysis on the dashboard: current period against year to date, last year and the three-year trend */
export default function TrendAnalysis({ data }: { data: Analytics }) {
  const can = useCan();
  const feature = useFeature();
  const mode = useUiStore((s) => s.mode);
  const showCosts = can("cost.view");
  const [metric, setMetric] = useState<Metric>("purchases");
  const [measure, setMeasure] = useState<Measure>("qty");
  // The client's preferred unit (feature flag) is the default; each user can switch, and the choice follows them
  const unitPref = usePreference<Unit | null>("dashboard:purchase-unit", null);
  const unit: Unit = unitPref.value ?? (feature("PACKING_UNIT_REPORTS") ? "packing" : "base");
  const field = METRIC_FIELDS[metric][measure === "value" && showCosts ? "value" : "qty"];
  const isValue = measure === "value" && showCosts;
  const format = isValue ? formatMoney : fmtQty;
  const badWhenUp = metric === "losses";

  const { tiles, yoy } = useMemo(() => {
    const today = dayjs(data.date);
    const year = today.year();
    const byMonth = new Map(data.months.map((m) => [m.month, Number(m[field] ?? 0)]));
    const get = (y: number, m: number) => byMonth.get(`${y}-${String(m).padStart(2, "0")}`) ?? 0;
    const sumYear = (y: number, upTo = 12) => Array.from({ length: upTo }, (_, i) => get(y, i + 1)).reduce((a, b) => a + b, 0);
    const month = today.month() + 1;
    const avg3 = (m: number) => (get(year - 1, m) + get(year - 2, m) + get(year - 3, m)) / 3;
    // Period totals compare like-for-like dates (this month so far against the same days last year); the monthly
    // series only has whole months, used for the chart and the three-year average of the months so far
    const totals = data.totals[metric];
    const t = (key: "mtd" | "mtd_ly" | "ytd" | "ytd_ly" | "last_year" | "avg_3y") =>
      Number((isValue ? totals[`${key}_value`] : totals[key]) ?? 0);
    return {
      tiles: {
        mtd: t("mtd"),
        mtdLy: t("mtd_ly"),
        ytd: t("ytd"),
        ytdLy: t("ytd_ly"),
        lastYear: t("last_year"),
        avg3y: t("avg_3y"),
        avg3yYtd: (sumYear(year - 1, month) + sumYear(year - 2, month) + sumYear(year - 3, month)) / 3,
      },
      yoy: Array.from({ length: 12 }, (_, i) => ({
        month: i + 1,
        this_year: i + 1 <= month ? get(year, i + 1) : null,
        last_year: get(year - 1, i + 1),
        avg_3y: avg3(i + 1),
      })),
    };
  }, [data, field, metric, isValue]);

  const rows = data[metric].rows;
  const inUnit = (r: ItemTrendRow, v: number) => (unit === "packing" && r.packing ? v / r.packing.factor : v);
  const unitCode = (r: ItemTrendRow) => (unit === "packing" && r.packing ? r.packing.uom.code : r.item.base_uom.code);
  const qtyCell = (key: keyof ItemTrendRow) => (_: unknown, r: ItemTrendRow) => <span className="wms-num">{fmtQty(inUnit(r, Number(r[key])))}</span>;
  const changeCell = (now: keyof ItemTrendRow, before: keyof ItemTrendRow) => (_: unknown, r: ItemTrendRow) => (
    <Delta now={Number(r[now])} before={Number(r[before])} badWhenUp={badWhenUp} />
  );
  const metricLabel = METRIC_FIELDS[metric].label;
  const year = dayjs(data.date).year();

  return (
    <Card
      title="Trend analysis"
      data-testid="trend-analysis"
      extra={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Segmented
            value={metric}
            onChange={(v) => setMetric(v as Metric)}
            options={[
              { value: "purchases", label: "Stock purchases" },
              { value: "losses", label: "Stock loss" },
            ]}
            aria-label="Metric"
          />
          {showCosts && (
            <Segmented
              value={measure}
              onChange={(v) => setMeasure(v as Measure)}
              options={[
                { value: "qty", label: "Quantity" },
                { value: "value", label: "Value" },
              ]}
              aria-label="Measure"
            />
          )}
        </div>
      }
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12.5, marginTop: -4 }}>
        {metric === "purchases" ? "Goods received from suppliers" : "Adjustments out and count losses"}
        {isValue ? (metric === "purchases" ? ", at purchase price" : ", at average purchase cost") : ", all SKUs in base units"}. Compared with the same
        period last year and the average of the three full years before {year}.
      </Typography.Paragraph>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} lg={6}>
          <PeriodTile label="This month" hint={`${dayjs(data.date).format("MMMM")} so far, against the same dates last year`} value={tiles.mtd} compare={tiles.mtdLy} compareLabel="last year" format={format} badWhenUp={badWhenUp} />
        </Col>
        <Col xs={12} lg={6}>
          <PeriodTile label="Year to date" hint="From 1 January to today, against the same dates last year" value={tiles.ytd} compare={tiles.ytdLy} compareLabel="last year" format={format} badWhenUp={badWhenUp} />
        </Col>
        <Col xs={12} lg={6}>
          <PeriodTile label="Year to date vs 3-year trend" hint={`This year so far against the average of January–${dayjs(data.date).format("MMMM")} over the three years before (whole months)`} value={tiles.ytd} compare={tiles.avg3yYtd} compareLabel="3-yr avg" format={format} badWhenUp={badWhenUp} />
        </Col>
        <Col xs={12} lg={6}>
          <PeriodTile label={`Last year (${year - 1})`} hint="The whole of last year, against the average year of the three before this one" value={tiles.lastYear} compare={tiles.avg3y} compareLabel="3-yr avg" format={format} badWhenUp={badWhenUp} />
        </Col>
      </Row>

      <TrendChart
        data={yoy}
        xKey="month"
        series={YOY_SERIES[mode]}
        xLabel={(v) => dayjs().month(Number(v) - 1).format("MMM")}
        xTitle="Month"
        format={format}
        testId="yoy-chart"
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "20px 0 8px" }}>
        <Typography.Text strong>
          {metricLabel} by SKU
          <Typography.Text type="secondary" style={{ fontWeight: 400, fontSize: 12.5 }}>
            {" "}· top {rows.length} of {data[metric].total} by quantity this year
          </Typography.Text>
        </Typography.Text>
        <Segmented
          size="small"
          value={unit}
          onChange={(v) => unitPref.loaded && unitPref.save(v as Unit)}
          options={[
            { value: "base", label: "Base unit" },
            { value: "packing", label: "Packing unit" },
          ]}
          aria-label="Quantity unit"
        />
      </div>
      <Table<ItemTrendRow>
        size="small"
        rowKey={(r) => r.item.id}
        dataSource={rows}
        pagination={rows.length > 10 ? { pageSize: 10, size: "small" } : false}
        scroll={{ x: "max-content" }}
        locale={emptyLocale(metric === "purchases" ? "No goods received in the last four years" : "No stock losses in the last four years")}
        columns={[
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span>, fixed: "left" },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Unit", render: (_, r) => unitCode(r) },
          { title: "Month to date", align: "right", render: qtyCell("mtd") },
          { title: "Same dates LY", align: "right", render: qtyCell("mtd_ly") },
          { title: "Change", align: "right", render: changeCell("mtd", "mtd_ly") },
          { title: "Year to date", align: "right", render: qtyCell("ytd") },
          { title: "Same dates LY", align: "right", render: qtyCell("ytd_ly") },
          { title: "Change", align: "right", render: changeCell("ytd", "ytd_ly") },
          { title: `Year ${year - 1}`, align: "right", render: qtyCell("last_year") },
          { title: "3-yr avg / year", align: "right", render: qtyCell("avg_3y") },
          ...(showCosts
            ? [
                { title: "YTD value", align: "right" as const, render: (_: unknown, r: ItemTrendRow) => <span className="wms-num">{formatMoney(r.ytd_value)}</span> },
                { title: "Change", align: "right" as const, render: (_: unknown, r: ItemTrendRow) => <Delta now={r.ytd_value ?? 0} before={r.ytd_ly_value ?? 0} badWhenUp={badWhenUp} /> },
              ]
            : []),
        ]}
      />
      {unit === "packing" && rows.some((r) => !r.packing) && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Items without a packing unit stay in their base unit.
        </Typography.Text>
      )}
    </Card>
  );
}
