import type { ReactNode } from "react";

import {
  AlertOutlined,
  ArrowRightOutlined,
  AuditOutlined,
  CarOutlined,
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
import { ErrorState, IconTile, Kpi, KpiStrip, PageHeader, Pill, SectionTitle, StatCard, type Accent } from "@/components/ui";
import { useMe } from "@/api/me";
import { useUiStore } from "@/stores/uiStore";

// Categorical slots 1 and 2 of the reference palette (validated with the palette script as distinguishable for color
// vision deficiency); dark mode uses lighter steps of the same hues so the lines keep their contrast on charcoal
const SERIES = {
  light: [
    { key: "received_qty", name: "Received", color: "#2a78d6" },
    { key: "shipped_qty", name: "Shipped", color: "#eb6834" },
  ],
  dark: [
    { key: "received_qty", name: "Received", color: "#4b93ea" },
    { key: "shipped_qty", name: "Shipped", color: "#f07f50" },
  ],
};

const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

function HealthRow({ icon, accent, label, value, to }: { icon: ReactNode; accent: Accent; label: string; value: number; to?: string }) {
  const body = (
    <>
      <IconTile icon={icon} accent={accent} size={28} />
      <Typography.Text type="secondary" style={{ flex: 1 }}>
        {label}
      </Typography.Text>
      <Typography.Text strong className="wms-num" style={{ fontSize: 15 }}>
        {fmt(value)}
      </Typography.Text>
      {to && <ArrowRightOutlined style={{ fontSize: 11, color: "var(--ant-color-text-quaternary)" }} aria-hidden />}
    </>
  );
  return to ? (
    <Link to={to} className="wms-list-row">
      {body}
    </Link>
  ) : (
    <div className="wms-list-row">{body}</div>
  );
}

function MiniMetric({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div>
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        {label}
      </Typography.Text>
      <div className="wms-num" style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.5, lineHeight: 1.25 }}>
        {fmt(value)}
      </div>
      {hint && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {hint}
        </Typography.Text>
      )}
    </div>
  );
}

/** Bin utilization: the label says the level in words, the bar color only reinforces it */
function utilization(usage: number): { tone: Accent; label: string; color?: string } {
  if (usage > 90) return { tone: "red", label: "Nearly full", color: "var(--wms-tone-red-fg)" };
  if (usage > 75) return { tone: "amber", label: "Filling up", color: "var(--wms-tone-amber-fg)" };
  return { tone: "green", label: "Healthy" };
}

/** Dashboard: today's activity, backlog, stock health, received/shipped trend over 14 days */
export default function DashboardPage() {
  const { data: me } = useMe();
  const mode = useUiStore((s) => s.mode);
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["reports", "dashboard"],
    queryFn: async () => (await apiClient.get<Dashboard>("/reports/dashboard")).data,
    // Live updates refetch it after every change; this only catches the date rolling over and missed events
    refetchInterval: 5 * 60_000,
  });
  const firstName = me?.display_name?.split(/\s+/)[0];
  const header = (
    <PageHeader
      title={`${greeting()}${firstName ? `, ${firstName}` : ""}`}
      description={data ? `${dayjs(data.date).format("dddd, MMMM D, YYYY")} · quantities in base units` : "Today's activity, open work and stock health at a glance"}
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12.5, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <SyncOutlined spin={isFetching} aria-hidden /> Updates within seconds of any change
        </Typography.Text>
      }
    />
  );

  if (isLoading)
    return (
      <>
        {header}
        <Skeleton active paragraph={{ rows: 10 }} />
      </>
    );
  if (!data)
    return (
      <>
        {header}
        <ErrorState title="Could not load the dashboard" error={error} onRetry={() => refetch()} />
      </>
    );

  const { today, backlog, stock } = data;
  const usage = stock.bins_total ? Math.round((stock.bins_used / stock.bins_total) * 100) : 0;
  const level = utilization(usage);
  const available = Math.max(0, stock.qty_on_hand - stock.qty_allocated);

  return (
    // No dimming while refreshing: with live updates that happens often, and flicker would be noise
    <div className="wms-dashboard" style={{ display: "grid", gap: 24 }}>
      {header}

      <div>
        <SectionTitle title="Today" />
        <KpiStrip label="Today's activity">
          <Kpi label="Received" value={today.received_qty} hint="Quantity put into stock" testId="tile-received" icon={<InboxOutlined aria-hidden />} />
          <Kpi label="Shipped" value={today.shipped_qty} hint="Quantity shipped out" testId="tile-shipped" icon={<CarOutlined aria-hidden />} />
          <Kpi label="Receipts posted" value={today.grn_posted} hint="Goods receipts" to="/grns" icon={<FileDoneOutlined aria-hidden />} />
          <Kpi label="Shipments posted" value={today.shipments_posted} hint="Shipments" to="/shipments" icon={<FileTextOutlined aria-hidden />} />
        </KpiStrip>
      </div>

      <div>
        <SectionTitle title="Work in progress" extra="Inbound to outbound · open a card to see the list" />
        <Row gutter={[12, 12]}>
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
              alert={backlog.shortage_lines > 0}
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
              series={SERIES[mode]}
              xLabel={(v) => dayjs(String(v)).format("MMM D")}
              testId="trend-chart"
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Stock health" style={{ height: "100%" }}>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={12}><MiniMetric label="SKUs in stock" value={stock.sku_count} /></Col>
              <Col span={12}><MiniMetric label="On hand" value={stock.qty_on_hand} /></Col>
              <Col span={12}><MiniMetric label="Available" value={available} hint="On hand minus allocated" /></Col>
              <Col span={12}><MiniMetric label="Allocated" value={stock.qty_allocated} hint="Reserved for orders" /></Col>
            </Row>

            <div className="wms-meter" style={{ marginBottom: 8 }}>
              <div className="wms-meter-head">
                <Typography.Text strong>Bin utilization</Typography.Text>
                <Pill tone={level.tone} dot>
                  {level.label}
                </Pill>
              </div>
              <Progress percent={usage} strokeColor={level.color} aria-label={`Bin utilization ${usage}%`} />
              <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
                {fmt(stock.bins_used)} of {fmt(stock.bins_total)} bins hold stock
              </Typography.Text>
            </div>

            <HealthRow icon={<WarningOutlined />} accent="amber" label="Expiring within 30 days" value={stock.expiring_30d_qty} to="/reports/expiry" />
            <HealthRow icon={<AlertOutlined />} accent="red" label="Expired" value={stock.expired_qty} to="/reports/expiry" />
          </Card>
        </Col>
      </Row>

      <OccupancyHeatmap />
    </div>
  );
}
