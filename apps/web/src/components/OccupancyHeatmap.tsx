import { useState } from "react";

import { LockOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Card, Segmented, Skeleton, Table, Tooltip, Typography } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { OccupancyArea } from "@/api/types";
import { useUiStore } from "@/stores/uiStore";

/**
 * One-hue ordinal ramps (blue), validated with the dataviz palette script against this app's card surfaces
 * (#ffffff light, #141726 dark): monotone lightness, visible steps, and the emptiest step still clears 2:1 against the
 * card. Dark mode has its own steps (empty zones sink toward the surface), not an inverted copy.
 */
const RAMP = {
  light: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"],
  dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"],
};
// Text on each step: dark ink on the light steps, white on the deep ones (all >= 4.5:1)
const INK = {
  light: ["#111827", "#111827", "#ffffff", "#ffffff", "#ffffff"],
  dark: ["#ffffff", "#ffffff", "#0b0d17", "#0b0d17", "#0b0d17"],
};
const LEVELS = ["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"];

const share = (a: OccupancyArea) => (a.bins_total ? a.bins_used / a.bins_total : 0);
const level = (a: OccupancyArea) => Math.min(4, Math.floor(share(a) * 5));
const pct = (a: OccupancyArea) => `${Math.round(share(a) * 100)}%`;
const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

function details(a: OccupancyArea) {
  const fill = a.capacity_qty ? ` · ${Math.round((a.qty_on_hand / a.capacity_qty) * 100)}% of capacity` : "";
  return (
    <div style={{ lineHeight: 1.6 }}>
      <div style={{ fontWeight: 600 }}>
        {a.code} {a.name !== a.code ? `· ${a.name}` : ""}
      </div>
      <div>
        {a.bins_used} of {a.bins_total} bins in use ({pct(a)})
      </div>
      <div>
        {fmt(a.qty_on_hand)} on hand{fill}
      </div>
      {a.bins_locked > 0 && <div>{a.bins_locked} bins locked</div>}
      <div style={{ opacity: 0.7 }}>{a.location_type === "WAREHOUSE" ? `Bins directly under warehouse ${a.warehouse_code}` : `Warehouse ${a.warehouse_code}`}</div>
    </div>
  );
}

function Legend({ mode }: { mode: "light" | "dark" }) {
  return (
    <div className="wms-heat-legend" aria-hidden>
      <span>Bins in use</span>
      {LEVELS.map((label, i) => (
        <span key={label} className="wms-heat-legend-step">
          <span className="wms-heat-swatch" style={{ background: RAMP[mode][i] }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/** Zone occupancy: share of bins holding stock, one tile per zone (bins outside any zone count under their warehouse) */
export default function OccupancyHeatmap() {
  const mode = useUiStore((s) => s.mode);
  const [view, setView] = useState<"map" | "table">("map");
  const { data } = useQuery({
    queryKey: ["reports", "occupancy"],
    queryFn: async () => (await apiClient.get<OccupancyArea[]>("/reports/occupancy")).data,
  });

  return (
    <Card
      title="Zone occupancy"
      extra={
        <Segmented
          size="small"
          value={view}
          onChange={(v) => setView(v as "map" | "table")}
          options={[{ label: "Map", value: "map" }, { label: "Table", value: "table" }]}
        />
      }
    >
      {!data ? (
        <Skeleton active />
      ) : !data.length ? (
        <Typography.Text type="secondary">
          No bins yet. Create BIN locations under <Link to="/locations">Locations</Link> to see occupancy here.
        </Typography.Text>
      ) : view === "map" ? (
        <>
          <div className="wms-heat-grid" data-testid="occupancy-heatmap">
            {data.map((a) => {
              const i = level(a);
              return (
                <Tooltip key={a.id} title={details(a)}>
                  <div
                    className="wms-heat-tile"
                    tabIndex={0}
                    aria-label={`${a.code}: ${a.bins_used} of ${a.bins_total} bins in use, ${pct(a)}${a.bins_locked ? `, ${a.bins_locked} locked` : ""}`}
                    style={{ background: RAMP[mode][i], color: INK[mode][i] }}
                  >
                    <div className="wms-heat-code">{a.code}</div>
                    <div className="wms-heat-value">{pct(a)}</div>
                    <div className="wms-heat-meta">
                      {a.bins_used}/{a.bins_total} bins
                      {a.bins_locked > 0 && (
                        <span title={`${a.bins_locked} locked`}>
                          {" · "}
                          <LockOutlined /> {a.bins_locked}
                        </span>
                      )}
                    </div>
                  </div>
                </Tooltip>
              );
            })}
          </div>
          <Legend mode={mode} />
        </>
      ) : (
        <Table<OccupancyArea>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data}
          columns={[
            { title: "Zone", key: "zone", render: (_, a) => (a.location_type === "WAREHOUSE" ? `${a.code} (no zone)` : `${a.code} · ${a.name}`) },
            { title: "Warehouse", dataIndex: "warehouse_code" },
            { title: "Bins in use", key: "used", align: "right", render: (_, a) => `${a.bins_used} / ${a.bins_total}`, sorter: (x, y) => share(x) - share(y) },
            { title: "Share", key: "share", align: "right", render: (_, a) => pct(a), defaultSortOrder: "descend", sorter: (x, y) => share(x) - share(y) },
            { title: "Locked", dataIndex: "bins_locked", align: "right" },
            { title: "On hand", dataIndex: "qty_on_hand", align: "right", render: fmt },
            { title: "Capacity", dataIndex: "capacity_qty", align: "right", render: (v: number | null) => (v == null ? "—" : fmt(v)) },
          ]}
        />
      )}
    </Card>
  );
}
