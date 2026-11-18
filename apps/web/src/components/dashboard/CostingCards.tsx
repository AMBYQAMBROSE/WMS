import { useState } from "react";

import { LockOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Skeleton, Table, Tooltip, Typography } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { useCan, useFeature } from "@/api/me";
import type { Analytics, Pricing, PricingRow, RecipeOverview, SupplierRow } from "@/api/types";
import { ItemSelect } from "@/components/selects";
import TrendChart from "@/components/TrendChart";
import { Pill, emptyLocale, formatMoney, formatPct, formatPrice, formatQty } from "@/components/ui";
import { useUiStore } from "@/stores/uiStore";

// One series: categorical slot 1 (light / dark step)
const COST_SERIES = {
  light: [{ key: "avg_cost", name: "Average cost per base unit", color: "#2a78d6" }],
  dark: [{ key: "avg_cost", name: "Average cost per base unit", color: "#3987e5" }],
};

const Restricted = () => (
  <Tooltip title="Visible only to users with the cost.view permission">
    <Pill tone="slate">
      <LockOutlined aria-hidden /> Costing
    </Pill>
  </Tooltip>
);

/** Purchase price trend per SKU, for costing: cost.view only (the API refuses everyone else) */
export function PricingTrendCard() {
  const mode = useUiStore((s) => s.mode);
  const [itemId, setItemId] = useState<string>();
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "pricing", itemId],
    queryFn: async () => (await apiClient.get<Pricing>("/reports/pricing", { params: { item_id: itemId } })).data,
    placeholderData: (previous) => previous,
    staleTime: 5 * 60_000,
  });
  const selected = data?.rows.find((r) => r.item.id === itemId) ?? data?.rows[0];
  // From the first month with a price, so the chart does not start with years of nothing
  const firstKnown = selected?.points.findIndex((p) => p.avg_cost !== null) ?? -1;
  const points = selected && firstKnown >= 0 ? selected.points.slice(Math.min(firstKnown, selected.points.length - 12)) : [];

  return (
    <Card
      title="Stock pricing trend"
      extra={<Restricted />}
      style={{ height: "100%" }}
      data-testid="pricing-trend"
    >
      {isLoading ? (
        <Skeleton active />
      ) : !data?.rows.length ? (
        <Typography.Text type="secondary">
          No priced receipts yet. Enter unit prices on purchase orders; each goods receipt then records what the stock cost.
        </Typography.Text>
      ) : (
        <>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap", marginBottom: 8 }}>
            <ItemSelect
              style={{ width: 280 }}
              placeholder="Choose an item"
              value={selected?.item.id}
              onChange={setItemId}
              aria-label="Item for the price trend"
            />
            {selected && (
              <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
                Latest <strong className="wms-num">{formatPrice(selected.latest_cost)}</strong> per {selected.item.base_uom.code}
                {selected.change_pct !== null && <> · {formatPct(selected.change_pct)} on a year ago</>}
              </Typography.Text>
            )}
          </div>
          {selected && points.length ? (
            <TrendChart
              data={points}
              xKey="month"
              series={COST_SERIES[mode]}
              xLabel={(v) => dayjs(String(v) + "-01").format("MMM YY")}
              xTitle="Month"
              format={(v) => formatPrice(v)}
              testId="pricing-chart"
            />
          ) : (
            <Typography.Text type="secondary">No priced receipts for this item in the last four years.</Typography.Text>
          )}
          <Table<PricingRow>
            size="small"
            style={{ marginTop: 12 }}
            rowKey={(r) => r.item.id}
            dataSource={data.rows}
            pagination={false}
            scroll={{ x: "max-content", y: 260 }}
            onRow={(r) => ({ onClick: () => setItemId(r.item.id), style: { cursor: "pointer" } })}
            rowClassName={(r) => (r.item.id === selected?.item.id ? "ant-table-row-selected" : "")}
            columns={[
              { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
              { title: "Item", render: (_, r) => r.item.name, ellipsis: true },
              { title: "Latest", align: "right", render: (_, r) => <span className="wms-num">{formatPrice(r.latest_cost)}</span> },
              { title: "Avg this year", align: "right", render: (_, r) => <span className="wms-num">{formatPrice(r.avg_cost_ytd)}</span> },
              { title: "A year ago", align: "right", render: (_, r) => <span className="wms-num">{formatPrice(r.cost_year_ago)}</span> },
              { title: "Change", align: "right", render: (_, r) => <span className="wms-num">{formatPct(r.change_pct)}</span> },
              {
                title: "Range (3 yrs)",
                align: "right",
                render: (_, r) => (r.min_cost === null ? "—" : <span className="wms-num">{formatPrice(r.min_cost)} – {formatPrice(r.max_cost)}</span>),
              },
            ]}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Weighted average cost per base unit of each month's receipts, excluding tax. Biggest spend over the last 12 months first.
          </Typography.Text>
        </>
      )}
    </Card>
  );
}

/** Top 5 suppliers this year, their credit terms and how settlement is going */
export function SupplierCard({ data }: { data: Analytics }) {
  const can = useCan();
  const showCosts = can("cost.view");
  const { suppliers } = data;
  return (
    <Card
      title="Top suppliers this year"
      extra={showCosts ? <Link to="/payables">All payables →</Link> : undefined}
      style={{ height: "100%" }}
      data-testid="supplier-card"
    >
      {showCosts && (
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col span={12}>
            <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>Outstanding</Typography.Text>
            <div className="wms-num" style={{ fontSize: 20, fontWeight: 600 }}>{formatMoney(suppliers.outstanding)}</div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{suppliers.open_receipts} open receipts</Typography.Text>
          </Col>
          <Col span={12}>
            <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>Overdue</Typography.Text>
            <div className="wms-num" style={{ fontSize: 20, fontWeight: 600, color: suppliers.overdue ? "var(--wms-tone-red-fg)" : undefined }}>
              {formatMoney(suppliers.overdue)}
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{suppliers.overdue_receipts} receipts past due</Typography.Text>
          </Col>
        </Row>
      )}
      <Table<SupplierRow>
        size="small"
        rowKey={(r) => r.partner.id}
        dataSource={suppliers.rows}
        pagination={false}
        scroll={{ x: "max-content" }}
        locale={emptyLocale("No goods received this year")}
        columns={[
          { title: "Supplier", render: (_, r) => <span title={r.partner.code}>{r.partner.name}</span> },
          {
            title: "Credit terms",
            render: (_, r) => (r.credit_terms_days ? `${r.credit_terms_days} days` : <span className="wms-empty-value">On receipt</span>),
          },
          ...(showCosts
            ? [
                { title: "Purchases YTD", align: "right" as const, render: (_: unknown, r: SupplierRow) => <span className="wms-num">{formatMoney(r.ytd_value)}</span> },
                { title: "Share", align: "right" as const, render: (_: unknown, r: SupplierRow) => (r.share_pct === null ? "—" : `${r.share_pct}%`) },
                {
                  title: "Outstanding",
                  align: "right" as const,
                  render: (_: unknown, r: SupplierRow) => (
                    <span className="wms-num">
                      {formatMoney(r.outstanding)}
                      {r.overdue ? <div style={{ color: "var(--wms-tone-red-fg)", fontSize: 12 }}>{formatMoney(r.overdue)} overdue</div> : null}
                    </span>
                  ),
                },
              ]
            : [{ title: "Received YTD", align: "right" as const, render: (_: unknown, r: SupplierRow) => <span className="wms-num">{formatQty(r.ytd_qty)}</span> }]),
          {
            title: <Tooltip title="Average days from receipt to settlement over the last 12 months">Days to settle</Tooltip>,
            align: "right",
            render: (_, r) =>
              r.avg_days_to_settle === null ? (
                <span className="wms-empty-value">—</span>
              ) : (
                <span className="wms-num">
                  {r.avg_days_to_settle}
                  {r.credit_terms_days !== null && r.avg_days_to_settle > (r.credit_terms_days ?? 0) ? (
                    <Pill tone="amber">late</Pill>
                  ) : null}
                </span>
              ),
          },
          { title: "On time", align: "right", render: (_, r) => (r.on_time_pct === null ? "—" : `${r.on_time_pct}%`) },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Ranked by {showCosts ? "purchase value" : "quantity received"} this year. Due dates come from each supplier's credit terms; mark receipts settled
        under {showCosts ? <Link to="/payables">Payables</Link> : "Payables"}.
      </Typography.Text>
    </Card>
  );
}

/** Recipes: cost per unit and what current stock can make (feature RECIPES) */
export function RecipeCard() {
  const can = useCan();
  const feature = useFeature();
  const enabled = feature("RECIPES") && can("recipe.read");
  const { data, isLoading } = useQuery({
    queryKey: ["recipes", "overview"],
    queryFn: async () => (await apiClient.get<RecipeOverview[]>("/recipes/overview")).data,
    enabled,
  });
  if (!enabled) return null;
  const showCosts = can("cost.view");
  return (
    <Card title="Recipes" extra={<Link to="/recipes">All recipes →</Link>} style={{ height: "100%" }} data-testid="recipe-card">
      <Table<RecipeOverview>
        size="small"
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        pagination={(data?.length ?? 0) > 8 ? { pageSize: 8, size: "small" } : false}
        scroll={{ x: "max-content" }}
        locale={emptyLocale("No recipes yet")}
        columns={[
          { title: "Recipe", render: (_, r) => <Link to={`/recipes?open=${r.id}`}>{r.name}</Link> },
          { title: "Product", render: (_, r) => <span className="wms-mono">{r.product.sku_code}</span> },
          ...(showCosts
            ? [
                {
                  title: "Cost / unit",
                  align: "right" as const,
                  render: (_: unknown, r: RecipeOverview) => (
                    <span className="wms-num">
                      {formatPrice(r.unit_cost)}
                      {!r.complete && (
                        <Tooltip title="Some components have no purchase price yet; the cost is incomplete">
                          {" "}
                          <Pill tone="amber">partial</Pill>
                        </Tooltip>
                      )}
                    </span>
                  ),
                },
              ]
            : []),
          { title: "Can make", align: "right", render: (_, r) => <strong className="wms-num">{formatQty(r.can_make)}</strong> },
          { title: "Limited by", render: (_, r) => (r.bottleneck ? <span className="wms-mono">{r.bottleneck.sku_code}</span> : "—") },
        ]}
      />
    </Card>
  );
}
