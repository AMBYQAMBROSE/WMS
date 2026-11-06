import { useEffect, useRef, useState } from "react";

import { Segmented, Table, theme } from "antd";

/**
 * Multi-series line chart (no chart library): 2px lines, light grid, direct labels at line ends, crosshair + tooltip listing every series,
 * switchable to a data table. Colors are assigned per series in fixed order (reference palette slots 1, 2, ...); text always uses body colors.
 */
export interface TrendSeries {
  key: string;
  name: string;
  color: string;
}

const HEIGHT = 240;
const PAD = { top: 16, right: 64, bottom: 28, left: 48 };

function niceMax(value: number) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= value / 4)! * magnitude;
  return Math.ceil(value / step) * step;
}

/** Read one series' value from a row (series keys are strings, rows any object) */
const num = (row: object | undefined, key: string) => Number((row as Record<string, unknown> | undefined)?.[key]) || 0;

const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export default function TrendChart<T extends object>({
  data,
  xKey,
  series,
  xLabel = (v) => String(v),
  testId,
}: {
  data: T[];
  xKey: keyof T;
  series: TrendSeries[];
  xLabel?: (value: unknown) => string;
  testId?: string;
}) {
  const { token } = theme.useToken();
  const INK = token.colorText;
  const INK_SECONDARY = token.colorTextSecondary;
  const INK_MUTED = token.colorTextTertiary;
  const GRID = token.colorBorderSecondary;
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const values = data.flatMap((d) => series.map((s) => num(d, s.key)));
  const yMax = niceMax(Math.max(0, ...values));
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (data.length <= 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.floor(plotW / 56)));

  const onMove = (event: React.PointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const index = data.length <= 1 ? 0 : Math.round((px / rect.width) * (data.length - 1));
    setHover(Math.min(data.length - 1, Math.max(0, index)));
  };

  // End labels: when two lines end close together, offset them vertically so the text does not overlap
  const last = data.length - 1;
  const endLabels = series
    .map((s) => ({ s, y: y(num(data[last], s.key)) }))
    .sort((a, b) => a.y - b.y)
    .reduce<{ s: TrendSeries; y: number }[]>((acc, cur) => {
      const prev = acc[acc.length - 1];
      acc.push({ ...cur, y: prev && cur.y - prev.y < 14 ? prev.y + 14 : cur.y });
      return acc;
    }, []);
  // After offsetting down, labels must not cover the x-axis dates: shift them all up if they overflow the plot area
  const overflow = (endLabels[endLabels.length - 1]?.y ?? 0) - (PAD.top + plotH - 6);
  if (overflow > 0) endLabels.forEach((label) => (label.y -= overflow));

  return (
    <div data-testid={testId}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
        {/* Legend: line keys match the chart */}
        <div style={{ display: "flex", gap: 16 }}>
          {series.map((s) => (
            <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, color: INK_SECONDARY, fontSize: 12 }}>
              <svg width="16" height="8" aria-hidden>
                <line x1="1" y1="4" x2="15" y2="4" stroke={s.color} strokeWidth="2" strokeLinecap="round" />
              </svg>
              {s.name}
            </span>
          ))}
        </div>
        <Segmented
          size="small"
          value={view}
          onChange={(v) => setView(v as "chart" | "table")}
          options={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "Table" },
          ]}
        />
      </div>

      {view === "table" ? (
        <Table
          size="small"
          pagination={false}
          rowKey={(r) => String(r[xKey])}
          dataSource={data}
          columns={[
            { title: "Date", render: (_, r) => xLabel(r[xKey]) },
            ...series.map((s) => ({ title: s.name, align: "right" as const, render: (_: unknown, r: T) => fmt(num(r, s.key)) })),
          ]}
        />
      ) : (
        <div ref={box} style={{ position: "relative" }}>
          <svg width={width} height={HEIGHT} role="img" aria-label={series.map((s) => s.name).join(", ") + " trend"}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={PAD.left + plotW} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth="1" />
                <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill={INK_MUTED}>
                  {fmt(t)}
                </text>
              </g>
            ))}
            {data.map((d, i) =>
              i % labelEvery === 0 || i === last ? (
                <text key={i} x={x(i)} y={HEIGHT - 8} textAnchor="middle" fontSize="11" fill={INK_MUTED}>
                  {xLabel(d[xKey])}
                </text>
              ) : null,
            )}
            {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke={INK_MUTED} strokeWidth="1" />}
            <defs>
              {series.map((s) => (
                <linearGradient key={s.key} id={`trend-fill-${s.key}`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={s.color} stopOpacity="0.16" />
                  <stop offset="100%" stopColor={s.color} stopOpacity="0" />
                </linearGradient>
              ))}
            </defs>
            {data.length > 1 &&
              series.map((s) => (
                <polygon
                  key={`area-${s.key}`}
                  className="wms-chart-area"
                  fill={`url(#trend-fill-${s.key})`}
                  points={`${x(0)},${PAD.top + plotH} ${data.map((d, i) => `${x(i)},${y(num(d, s.key))}`).join(" ")} ${x(last)},${PAD.top + plotH}`}
                />
              ))}
            {series.map((s) => (
              <polyline
                key={s.key}
                className="wms-chart-line"
                pathLength={1}
                fill="none"
                stroke={s.color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                points={data.map((d, i) => `${x(i)},${y(num(d, s.key))}`).join(" ")}
              />
            ))}
            {hover !== null &&
              series.map((s) => (
                <circle key={s.key} cx={x(hover)} cy={y(num(data[hover], s.key))} r="4" fill={s.color} stroke={token.colorBgContainer} strokeWidth="2" />
              ))}
            {last >= 0 &&
              endLabels.map(({ s, y: ly }) => (
                <text key={s.key} x={x(last) + 8} y={ly} dy="0.32em" fontSize="12" fill={INK}>
                  {fmt(num(data[last], s.key))}
                </text>
              ))}
            {/* Transparent hit layer much larger than the lines, so the pointer works anywhere on the chart */}
            <rect
              x={PAD.left}
              y={PAD.top}
              width={plotW}
              height={plotH}
              fill="transparent"
              onPointerMove={onMove}
              onPointerLeave={() => setHover(null)}
            />
          </svg>
          {hover !== null && (
            <div className="wms-chart-tooltip" style={{ top: PAD.top, left: Math.min(x(hover) + 12, width - 170) }}>
              <div style={{ fontSize: 12, color: INK_SECONDARY, marginBottom: 4 }}>{xLabel(data[hover][xKey])}</div>
              {series.map((s) => (
                <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <svg width="12" height="8" aria-hidden>
                    <line x1="1" y1="4" x2="11" y2="4" stroke={s.color} strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <strong style={{ color: INK }}>{fmt(num(data[hover], s.key))}</strong>
                  <span style={{ color: INK_SECONDARY }}>{s.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
