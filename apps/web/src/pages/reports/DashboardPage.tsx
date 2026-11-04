import type { ReactNode } from "react";

import {
  AlertOutlined,
  AuditOutlined,
  CarOutlined,
  ClockCircleOutlined,
  ContainerOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  InboxOutlined,
  ShoppingCartOutlined,
  SyncOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Card, Col, Progress, Row, Skeleton, Typography } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { Dashboard } from "@/api/types";
import OccupancyHeatmap from "@/components/OccupancyHeatmap";
import TrendChart from "@/components/TrendChart";
import { IconTile, SectionTitle, StatCard, type Accent } from "@/components/ui";
import { useMe } from "@/api/me";

// Categorical slots 1 and 2 of the reference palette (validated with the palette script as distinguishable for color vision deficiency)
const SERIES = [
  { key: "received_qty", name: "Received", color: "#2a78d6" },
  { key: "shipped_qty", name: "Shipped", color: "#eb6834" },
];

const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

function HeroMetric({ label, value, testId, to }: { label: string; value: number; testId?: string; to?: string }) {
  const body = (
    <div data-testid={testId} style={{ minWidth: 120 }}>
      <div style={{ fontSize: 12, opacity: 0.7, fontWeight: 500, textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: -1, lineHeight: 1.2, color: "#fff" }}>{fmt(value)}</div>
    </div>
  );
  return to ? <Link to={to} style={{ color: "inherit" }}>{body}</Link> : body;
}

function HealthRow({ icon, accent, label, value, to }: { icon: ReactNode; accent: Accent; label: string; value: number; to?: string }) {
  const row = (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0" }}>
      <IconTile icon={icon} accent={accent} size={34} />
      <Typography.Text type="secondary" style={{ flex: 1 }}>{label}</Typography.Text>
      <Typography.Text strong style={{ fontSize: 16 }}>{fmt(value)}</Typography.Text>
    </div>
  );
  return to ? <Link to={to} style={{ color: "inherit", display: "block" }}>{row}</Link> : row;
}

/** Dashboard (Ninso DashboardSummary): today's activity, backlog, stock health, received/shipped trend over 14 days */
export default function DashboardPage() {
  const { data: me } = useMe();
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["reports", "dashboard"],
    queryFn: async () => (await apiClient.get<Dashboard>("/reports/dashboard")).data,
    // Live updates refetch it after every change; this only catches the date rolling over and missed events
    refetchInterval: 5 * 60_000,
  });
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />;
  const { today, backlog, stock } = data;
  const usage = stock.bins_total ? Math.round((stock.bins_used / stock.bins_total) * 100) : 0;
  const firstName = me?.display_name?.split(/\s+/)[0];

  return (
    // No dimming while refreshing: with live updates that happens often, and flicker would be noise
    <div style={{ display: "grid", gap: 24 }}>
      <section className="wms-hero">
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 24, alignItems: "flex-end" }}>
          <div>
            <div style={{ fontSize: 13, opacity: 0.75, display: "flex", alignItems: "center", gap: 6 }}>
              <ClockCircleOutlined /> {dayjs(data.date).format("dddd, MMMM D, YYYY")}
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, margin: "6px 0 4px", letterSpacing: -0.4 }}>
              {greeting()}{firstName ? `, ${firstName}` : ""}
            </div>
            <div style={{ fontSize: 13, opacity: 0.7, display: "flex", alignItems: "center", gap: 6 }}>
              <SyncOutlined spin={isFetching} /> Quantities in base units · updates live as work is done
            </div>
          </div>
          <div style={{ display: "flex", gap: 40, flexWrap: "wrap" }}>
            <HeroMetric label="Received today" value={today.received_qty} testId="tile-received" />
            <HeroMetric label="Shipped today" value={today.shipped_qty} testId="tile-shipped" />
            <HeroMetric label="Receipts posted" value={today.grn_posted} to="/grns" />
            <HeroMetric label="Shipments posted" value={today.shipments_posted} to="/shipments" />
          </div>
        </div>
      </section>

      <div>
        <SectionTitle title="Work in progress" extra="Click a card to open the list" />
        <Row gutter={[16, 16]}>
          <Col xs={12} md={8} xl={6}><StatCard label="Open purchase orders" value={backlog.po_open} to="/purchase-orders" icon={<FileTextOutlined />} accent="indigo" hint="Awaiting delivery" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="Receipts to post" value={backlog.grn_draft} to="/grns" icon={<InboxOutlined />} accent="cyan" hint="Draft goods receipts" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="To put away" value={backlog.putaway_draft} to="/putaways" icon={<ContainerOutlined />} accent="blue" hint="Goods waiting at the dock" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="Counts in progress" value={backlog.count_open} to="/cycle-counts" icon={<AuditOutlined />} accent="violet" hint="Open cycle counts" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="Sales orders in progress" value={backlog.so_open} to="/sales-orders" icon={<ShoppingCartOutlined />} accent="indigo" hint="Not yet fully shipped" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="Pick lists to pick" value={backlog.pick_open} to="/picks" icon={<FileDoneOutlined />} accent="green" hint="Waiting for pickers" /></Col>
          <Col xs={12} md={8} xl={6}><StatCard label="Shipments to post" value={backlog.shipment_draft} to="/shipments" icon={<CarOutlined />} accent="amber" hint="Loaded, not yet posted" /></Col>
          <Col xs={12} md={8} xl={6}>
            <StatCard
              label="Shortage lines"
              value={backlog.shortage_lines}
              to="/shortages"
              icon={<AlertOutlined />}
              accent={backlog.shortage_lines ? "red" : "slate"}
              hint={backlog.shortage_lines ? "Needs attention" : "All orders covered"}
              testId="tile-shortage"
            />
          </Col>
        </Row>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="Received vs shipped" extra={<Typography.Text type="secondary">Last 14 days</Typography.Text>} style={{ height: "100%" }}>
            <TrendChart
              data={data.trend}
              xKey="date"
              series={SERIES}
              xLabel={(v) => dayjs(String(v)).format("M/D")}
              testId="trend-chart"
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Stock health" style={{ height: "100%" }}>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>SKUs in stock</Typography.Text>
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5 }}>{fmt(stock.sku_count)}</div>
              </Col>
              <Col span={12}>
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>Quantity on hand</Typography.Text>
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5 }}>{fmt(stock.qty_on_hand)}</div>
              </Col>
            </Row>

            <div style={{ padding: 14, borderRadius: 12, background: "var(--ant-color-fill-quaternary)", marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <Typography.Text strong>Bin utilization</Typography.Text>
                <Typography.Text type="secondary">
                  {fmt(stock.bins_used)} / {fmt(stock.bins_total)} bins
                </Typography.Text>
              </div>
              <Progress
                percent={usage}
                strokeColor={usage > 90 ? "#dc2626" : usage > 75 ? "#d97706" : { from: "#4f46e5", to: "#06b6d4" }}
                strokeLinecap="round"
              />
            </div>

            <HealthRow icon={<WarningOutlined />} accent="amber" label="Expiring within 30 days" value={stock.expiring_30d_qty} to="/reports/expiry" />
            <HealthRow icon={<AlertOutlined />} accent="red" label="Expired" value={stock.expired_qty} to="/reports/expiry" />
            <HealthRow icon={<ShoppingCartOutlined />} accent="indigo" label="Allocated to orders" value={stock.qty_allocated} />
          </Card>
        </Col>
      </Row>

      <OccupancyHeatmap />
    </div>
  );
}
