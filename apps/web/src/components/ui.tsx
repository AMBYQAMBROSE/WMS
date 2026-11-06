import type { CSSProperties, ReactNode } from "react";

import { ArrowRightOutlined, CheckCircleFilled, InboxOutlined, MinusOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import { Link } from "react-router";

import { HistoryButton } from "@/components/AuditTrail";
import { PhotosButton } from "@/components/DocumentPhotos";
import StatusTag from "@/components/StatusTag";
import { ACCENTS, type Accent } from "@/theme";

export { ACCENTS, type Accent };

export function PageHeader({
  title,
  description,
  extra,
}: {
  title: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div className="wms-page-header">
      <div style={{ minWidth: 0 }}>
        <Typography.Title level={2} className="wms-page-title">
          {title}
        </Typography.Title>
        {description && (
          <Typography.Paragraph type="secondary" className="wms-page-desc" style={{ marginBottom: 0 }}>
            {description}
          </Typography.Paragraph>
        )}
      </div>
      {extra && <div className="wms-toolbar-group">{extra}</div>}
    </div>
  );
}

/** One-row toolbar above a list: filters/search on the left, primary actions on the right */
export function Toolbar({ left, right, style }: { left?: ReactNode; right?: ReactNode; style?: CSSProperties }) {
  return (
    <div className="wms-toolbar" style={style}>
      <div className="wms-toolbar-group">{left}</div>
      {right && <div className="wms-toolbar-group">{right}</div>}
    </div>
  );
}

const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function StatCard({
  label,
  value,
  icon,
  accent = "indigo",
  hint,
  to,
  testId,
}: {
  label: string;
  value: number | string;
  icon?: ReactNode;
  accent?: Accent;
  hint?: ReactNode;
  to?: string;
  testId?: string;
}) {
  const a = ACCENTS[accent];
  const body = (
    <>
      <div className="wms-stat-top">
        <span className="wms-stat-label">{label}</span>
        {icon && (
          <span className="wms-stat-icon" style={{ color: a.fg, background: a.bg }}>
            {icon}
          </span>
        )}
      </div>
      <div className="wms-stat-value">{typeof value === "number" ? fmt(value) : value}</div>
      {(hint || to) && (
        <div className="wms-stat-hint">
          {hint}
          {to && <ArrowRightOutlined className="wms-stat-arrow" />}
        </div>
      )}
    </>
  );
  const style = { "--wms-stat-accent": a.fg } as CSSProperties;
  return to ? (
    <Link to={to} className="wms-stat" style={style} data-testid={testId}>
      {body}
    </Link>
  ) : (
    <div className="wms-stat" style={style} data-testid={testId}>
      {body}
    </div>
  );
}

export function SectionTitle({ title, extra }: { title: ReactNode; extra?: ReactNode }) {
  return (
    <div className="wms-section-title">
      <h3>{title}</h3>
      {extra && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{extra}</Typography.Text>}
    </div>
  );
}

export function EmptyState({ title = "Nothing here yet", hint }: { title?: string; hint?: ReactNode }) {
  return (
    <div className="wms-empty">
      <div className="wms-empty-icon">
        <InboxOutlined />
      </div>
      <div style={{ fontWeight: 600, color: "var(--ant-color-text-secondary)" }}>{title}</div>
      {hint && <div style={{ fontSize: 12, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

/** Header of a document detail card: document type, number, status and (with historyOf) the change history */
export function DocTitle({ label, no, status, historyOf }: { label: string; no: string; status?: string; historyOf?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0", flexWrap: "wrap" }}>
      <div style={{ lineHeight: 1.25 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: "var(--ant-color-text-tertiary)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          {label}
        </div>
        <div className="wms-mono" style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.3 }}>
          {no}
        </div>
      </div>
      {status && <StatusTag status={status} />}
      {historyOf && <HistoryButton entityId={historyOf} title={`${label} ${no}`} />}
      {historyOf && <PhotosButton documentId={historyOf} title={`${label} ${no}`} />}
    </div>
  );
}

/** Sticky action bar at the bottom of a create/edit form; the primary action (first child) sits on the far right */
export function FormFooter({ children }: { children: ReactNode }) {
  return <div className="wms-form-footer">{children}</div>;
}

/** Boolean cell: a check for yes, a muted dash for no */
export function YesNo({ value }: { value: boolean }) {
  return value ? (
    <CheckCircleFilled style={{ color: ACCENTS.green.fg }} aria-label="Yes" />
  ) : (
    <MinusOutlined style={{ color: "var(--ant-color-text-quaternary)" }} aria-label="No" />
  );
}

/** Small rounded icon tile */
export function IconTile({ icon, accent = "indigo", size = 32 }: { icon: ReactNode; accent?: Accent; size?: number }) {
  const a = ACCENTS[accent];
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: size / 3.2,
        display: "inline-grid",
        placeItems: "center",
        color: a.fg,
        background: a.bg,
        fontSize: size / 2,
        flexShrink: 0,
      }}
    >
      {icon}
    </span>
  );
}

export function BrandMark({ size = 34 }: { size?: number }) {
  return (
    <span className="wms-brand-mark" style={{ width: size, height: size }}>
      <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M3 9.5 12 4l9 5.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5Z" fill="rgba(255,255,255,0.18)" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
        <rect x="7" y="12" width="4" height="4" rx="0.8" fill="#fff" />
        <rect x="13" y="12" width="4" height="4" rx="0.8" fill="#fff" opacity="0.7" />
        <rect x="7" y="17" width="10" height="2" rx="0.8" fill="#fff" opacity="0.5" />
      </svg>
    </span>
  );
}
