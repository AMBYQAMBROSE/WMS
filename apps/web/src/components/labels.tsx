import { useState, type ReactNode } from "react";

import { PrinterOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Form, InputNumber, Modal, Select, Typography } from "antd";

import { apiClient } from "@/api/client";
import { openPdf } from "@/api/print";
import type { LabelLayout, LabelProfile } from "@/api/types";

export type Purpose = "ITEM" | "LOCATION" | "STOCK";

export const PURPOSE_LABELS: Record<Purpose, string> = { ITEM: "Item labels", LOCATION: "Location labels", STOCK: "Stock labels" };

type Geometry = Pick<
  LabelLayout,
  | "media" | "label_width_mm" | "label_height_mm" | "page_width_mm" | "page_height_mm" | "columns" | "rows"
  | "margin_top_mm" | "margin_left_mm" | "gap_x_mm" | "gap_y_mm"
>;

const sheet = (w: number, h: number, columns: number, rows: number, top: number, left = 0, gapX = 0, gapY = 0): Geometry => ({
  media: "SHEET", label_width_mm: w, label_height_mm: h, page_width_mm: 210, page_height_mm: 297, columns, rows,
  margin_top_mm: top, margin_left_mm: left, gap_x_mm: gapX, gap_y_mm: gapY,
});
const roll = (w: number, h: number): Geometry => ({
  media: "ROLL", label_width_mm: w, label_height_mm: h, page_width_mm: 210, page_height_mm: 297, columns: 1, rows: 1,
  margin_top_mm: 0, margin_left_mm: 0, gap_x_mm: 0, gap_y_mm: 0,
});

/** Common label stock, to start a profile from; every value can still be adjusted */
export const LABEL_PRESETS: { key: string; label: string; geometry: Geometry }[] = [
  { key: "a4-3x8", label: "A4 sheet, 3 × 8 labels of 70 × 36 mm", geometry: sheet(70, 36, 3, 8, 4.5) },
  { key: "a4-3x7", label: "A4 sheet, 3 × 7 labels of 70 × 42.3 mm", geometry: sheet(70, 42.3, 3, 7, 0.4) },
  { key: "a4-2x8", label: "A4 sheet, 2 × 8 labels of 99.1 × 33.9 mm", geometry: sheet(99.1, 33.9, 2, 8, 12.9, 4.65, 2.5, 0) },
  { key: "a4-2x5", label: "A4 sheet, 2 × 5 labels of 100 × 55 mm", geometry: sheet(100, 55, 2, 5, 10, 5) },
  { key: "a4-2x4", label: "A4 sheet, 2 × 4 labels of 105 × 74 mm", geometry: sheet(105, 74, 2, 4, 0.5) },
  { key: "a4-1x1", label: "A4 sheet, one label per page", geometry: sheet(200, 287, 1, 1, 5, 5) },
  { key: "roll-40x25", label: "Thermal roll, 40 × 25 mm", geometry: roll(40, 25) },
  { key: "roll-50x30", label: "Thermal roll, 50 × 30 mm", geometry: roll(50, 30) },
  { key: "roll-60x40", label: "Thermal roll, 60 × 40 mm", geometry: roll(60, 40) },
  { key: "roll-100x50", label: "Thermal roll, 100 × 50 mm", geometry: roll(100, 50) },
  { key: "roll-100x150", label: "Thermal roll, 100 × 150 mm (shipping label)", geometry: roll(100, 150) },
];

export const describeMedia = (p: Geometry) =>
  p.media === "ROLL"
    ? "Roll, one label per page"
    : `${pageName(p.page_width_mm, p.page_height_mm)} sheet, ${p.columns} × ${p.rows} = ${p.columns * p.rows} per page`;

export const describeSize = (p: Geometry) => `${fmt(p.label_width_mm)} × ${fmt(p.label_height_mm)} mm`;

function pageName(w: number, h: number) {
  if (w === 210 && h === 297) return "A4";
  if (w === 215.9 && h === 279.4) return "Letter";
  return `${fmt(w)} × ${fmt(h)} mm`;
}

const fmt = (v: number) => Number(v.toFixed(2)).toString();

/** How much of the page the labels take; over 100% the layout is refused on save */
export function sheetUsage(p: Geometry): { width: number; height: number } {
  return {
    width: p.margin_left_mm + p.columns * p.label_width_mm + (p.columns - 1) * p.gap_x_mm,
    height: p.margin_top_mm + p.rows * p.label_height_mm + (p.rows - 1) * p.gap_y_mm,
  };
}

/** To-scale sketch of the page (or one roll label), so a layout can be judged before a test print */
export function LabelPreview({ layout }: { layout: Partial<LabelLayout> }) {
  const g = { ...LABEL_PRESETS[0]!.geometry, ...stripEmpty(layout) } as LabelLayout;
  const isRoll = g.media === "ROLL";
  const pageW = isRoll ? g.label_width_mm : g.page_width_mm;
  const pageH = isRoll ? g.label_height_mm : g.page_height_mm;
  const columns = isRoll ? 1 : g.columns;
  const rows = isRoll ? 1 : g.rows;
  const cells: ReactNode[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const x = isRoll ? 0 : g.margin_left_mm + c * (g.label_width_mm + g.gap_x_mm);
      const y = isRoll ? 0 : g.margin_top_mm + r * (g.label_height_mm + g.gap_y_mm);
      cells.push(<LabelSketch key={`${r}-${c}`} x={x} y={y} layout={g} />);
    }
  }
  const usage = sheetUsage(g);
  const overflow = !isRoll && (usage.width > g.page_width_mm + 0.001 || usage.height > g.page_height_mm + 0.001);
  return (
    <div className="wms-label-preview">
      <svg viewBox={`-2 -2 ${pageW + 4} ${pageH + 4}`} role="img" aria-label="Label layout preview">
        <rect x={0} y={0} width={pageW} height={pageH} className="wms-label-page" />
        {cells}
      </svg>
      <Typography.Text type={overflow ? "danger" : "secondary"} style={{ fontSize: 12.5 }}>
        {isRoll
          ? `One ${describeSize(g)} label per page`
          : overflow
            ? `Labels need ${fmt(usage.width)} × ${fmt(usage.height)} mm, more than the ${fmt(g.page_width_mm)} × ${fmt(g.page_height_mm)} mm page`
            : `${columns * rows} labels per page, using ${fmt(usage.width)} × ${fmt(usage.height)} mm of ${fmt(g.page_width_mm)} × ${fmt(g.page_height_mm)} mm`}
      </Typography.Text>
    </div>
  );
}

function LabelSketch({ x, y, layout }: { x: number; y: number; layout: LabelLayout }) {
  const w = layout.label_width_mm;
  const h = layout.label_height_mm;
  const pad = Math.min(layout.padding_mm ?? 2, w / 3, h / 3);
  const innerW = w - 2 * pad;
  const innerH = h - 2 * pad;
  const qr = layout.barcode_type === "QR";
  const hasText = (layout.fields ?? []).length > 0;
  const q = Math.min(innerH, hasText ? innerW / 2 : innerW);
  const textX = pad + q + 2;
  const textW = innerW - q - 2;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width={w} height={h} className="wms-label-cell" rx={Math.min(1.5, w / 20)} />
      {qr ? (
        <>
          <rect x={pad} y={pad + (innerH - q) / 2} width={q} height={q} className="wms-label-code" />
          {hasText && textW > 0 && [0, 1, 2].map((i) => (
            <rect key={i} x={textX} y={pad + i * innerH * 0.18} width={textW * (i ? 0.7 : 1)} height={innerH * 0.1} className="wms-label-text" />
          ))}
        </>
      ) : (
        <>
          {hasText && <rect x={pad + innerW * 0.1} y={pad} width={innerW * 0.8} height={innerH * 0.14} className="wms-label-text" />}
          <rect x={pad + innerW * 0.05} y={pad + innerH * (hasText ? 0.24 : 0)} width={innerW * 0.9} height={innerH * (hasText ? 0.5 : 1)} className="wms-label-code" />
          {hasText && <rect x={pad + innerW * 0.25} y={pad + innerH * 0.82} width={innerW * 0.5} height={innerH * 0.12} className="wms-label-text" />}
        </>
      )}
    </g>
  );
}

function stripEmpty<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== null && v !== undefined)) as Partial<T>;
}

export function useLabelProfiles(purpose: Purpose) {
  return useQuery({
    queryKey: ["label-profiles", purpose],
    queryFn: async () => (await apiClient.get<LabelProfile[]>("/label-profiles", { params: { purpose } })).data,
  });
}

interface PrintValues {
  profile_id?: string;
  copies: number;
  skip: number;
}

/**
 * Asks how to print (profile, copies, blank positions to skip on a used sheet), then opens the PDF.
 * `body` is the request without those options: which items or locations to print.
 */
export function PrintLabelsModal({
  open,
  purpose,
  path,
  body,
  summary,
  maxCopies,
  onClose,
  children,
}: {
  open: boolean;
  purpose: Purpose;
  path: string;
  body: Record<string, unknown>;
  summary: ReactNode;
  maxCopies: number;
  onClose: () => void;
  /** Extra form items whose values are sent with the request (e.g. which area to print) */
  children?: ReactNode;
}) {
  const [form] = Form.useForm<PrintValues>();
  const [busy, setBusy] = useState(false);
  const { data: profiles, isLoading } = useLabelProfiles(purpose);
  const profileId = Form.useWatch("profile_id", form);
  const chosen = profiles?.find((p) => p.id === profileId) ?? profiles?.find((p) => p.is_default);
  const isSheet = (chosen?.media ?? "SHEET") === "SHEET";

  const submit = async (v: PrintValues) => {
    setBusy(true);
    const ok = await openPdf(path, { ...body, ...v, skip: isSheet ? v.skip : 0 });
    setBusy(false);
    if (ok) onClose();
  };

  return (
    <Modal
      open={open}
      title={`Print ${PURPOSE_LABELS[purpose].toLowerCase()}`}
      okText="Print"
      okButtonProps={{ icon: <PrinterOutlined /> }}
      onOk={() => form.submit()}
      confirmLoading={busy}
      onCancel={onClose}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">{summary}</Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{ copies: 1, skip: 0 }}
        onFinish={(v) => void submit(v)}
      >
        {children}
        <Form.Item
          name="profile_id"
          label="Label layout"
          extra={profiles && !profiles.length ? "No layouts set up yet: the built-in A4 layout is used. Set up layouts under System > Labels & printing." : undefined}
        >
          <Select
            loading={isLoading}
            allowClear
            placeholder={profiles?.some((p) => p.is_default) ? "Default layout" : "Built-in A4 layout"}
            options={profiles?.map((p) => ({ value: p.id, label: `${p.name}${p.is_default ? " (default)" : ""} · ${describeSize(p)}` }))}
            data-testid="label-profile"
          />
        </Form.Item>
        <Form.Item name="copies" label="Copies of each label" rules={[{ required: true }]}>
          <InputNumber min={1} max={maxCopies} precision={0} style={{ width: 160 }} data-testid="label-copies" />
        </Form.Item>
        {isSheet && (
          <Form.Item
            name="skip"
            label="Skip label positions"
            extra="On a partly used sheet: how many positions at the top are already used. Printing starts after them."
          >
            <InputNumber min={0} max={999} precision={0} style={{ width: 160 }} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}

/** Toolbar button that opens PrintLabelsModal */
export function PrintLabelsButton({ disabled, onClick, children }: { disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Button icon={<PrinterOutlined />} disabled={disabled} onClick={onClick}>
      {children}
    </Button>
  );
}
