import { useState } from "react";

import { AlertOutlined, DownloadOutlined, DownOutlined } from "@ant-design/icons";
import { Button, Card, Dropdown, Table, Typography } from "antd";
import { Link } from "react-router";

import { useCan } from "@/api/me";
import type { StockAlertRow, StockAlerts } from "@/api/types";
import { exportReport } from "@/components/reports";
import { Pill, emptyLocale, formatQty } from "@/components/ui";

const LEVEL = {
  out: { tone: "red", label: "Out of stock" },
  below: { tone: "red", label: "Below minimum" },
  low: { tone: "amber", label: "Near minimum" },
} as const;

const isAlarm = (r: StockAlertRow) => r.level === "out" || r.level === "below";

/** Banner at the top of the dashboard: blinks red while any item is below its stock buffer */
export function StockAlarmBanner({ alerts }: { alerts: StockAlerts }) {
  if (!alerts.alarm_count) return null;
  const first = alerts.rows.filter(isAlarm).slice(0, 3);
  return (
    <a
      href="#stock-buffer"
      className="wms-alarm wms-alarm-blink"
      role="alert"
      data-testid="stock-alarm"
      style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", textDecoration: "none" }}
    >
      <span className="wms-alarm-dot" aria-hidden />
      <AlertOutlined aria-hidden style={{ fontSize: 18 }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        <strong>
          {alerts.alarm_count} item{alerts.alarm_count === 1 ? "" : "s"} below minimum stock
          {alerts.out_count ? ` (${alerts.out_count} out of stock)` : ""}
        </strong>
        <span style={{ marginLeft: 8, opacity: 0.85 }}>
          {first.map((r) => r.item.sku_code).join(", ")}
          {alerts.alarm_count > first.length ? ", …" : ""}
        </span>
      </span>
      <span style={{ whiteSpace: "nowrap", fontWeight: 600 }}>Review ↓</span>
    </a>
  );
}

/** Items at or under their stock buffer: alarms (below minimum) blink red, warnings (within 25% above) are amber */
export function StockBufferCard({ alerts }: { alerts: StockAlerts }) {
  const can = useCan();
  return (
    <Card
      id="stock-buffer"
      title="Stock buffer"
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
          {alerts.alarm_count ? `${alerts.alarm_count} below minimum` : "Nothing below minimum"}
          {alerts.warning_count ? ` · ${alerts.warning_count} near it` : ""}
        </Typography.Text>
      }
      style={{ height: "100%" }}
    >
      <Table<StockAlertRow>
        size="small"
        rowKey={(r) => r.item.id}
        dataSource={alerts.rows}
        pagination={alerts.rows.length > 8 ? { pageSize: 8, size: "small" } : false}
        scroll={{ x: "max-content" }}
        rowClassName={(r) => (isAlarm(r) ? "wms-alarm-row" : "")}
        locale={emptyLocale(
          can("item.update")
            ? "No item is near its minimum stock. Set a minimum stock on items (Master data → Items) to be alarmed here."
            : "No item is near its minimum stock",
        )}
        columns={[
          {
            title: "Item",
            render: (_, r) => (
              <Link to={`/stock?item=${r.item.id}`}>
                <span className="wms-mono">{r.item.sku_code}</span> {r.item.name}
              </Link>
            ),
          },
          {
            title: "Status",
            render: (_, r) => (
              <span className={isAlarm(r) ? "wms-alarm-blink" : undefined} style={{ display: "inline-block", borderRadius: 999 }}>
                <Pill tone={LEVEL[r.level as keyof typeof LEVEL]?.tone ?? "amber"} dot>
                  {LEVEL[r.level as keyof typeof LEVEL]?.label ?? r.level}
                </Pill>
              </span>
            ),
          },
          { title: "Available", align: "right", render: (_, r) => <span className="wms-num">{formatQty(r.available)}</span> },
          { title: "Minimum", align: "right", render: (_, r) => <span className="wms-num">{formatQty(r.min_stock_qty)}</span> },
          {
            title: "Short by",
            align: "right",
            render: (_, r) => (r.shortfall > 0 ? <strong className="wms-num">{formatQty(r.shortfall)} {r.item.base_uom.code}</strong> : <span className="wms-empty-value">—</span>),
          },
        ]}
      />
    </Card>
  );
}

/** Real-time stock on hand as CSV (for finance or whoever asks): by location and batch, or one row per item */
export function StockExportButton() {
  const can = useCan();
  const [busy, setBusy] = useState(false);
  if (!can("stock.read")) return null;
  const run = async (by: "location" | "item") => {
    setBusy(true);
    try {
      await exportReport("/reports/stock-on-hand", { by });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: [
          { key: "item", label: "One row per item (totals)", onClick: () => void run("item") },
          { key: "location", label: "By location and batch", onClick: () => void run("location") },
        ],
      }}
    >
      <Button icon={<DownloadOutlined />} loading={busy} data-testid="export-stock">
        Export stock on hand (CSV) <DownOutlined style={{ fontSize: 10 }} />
      </Button>
    </Dropdown>
  );
}
