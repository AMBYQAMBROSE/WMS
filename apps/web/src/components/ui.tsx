import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckCircleFilled,
  CheckOutlined,
  CloseOutlined,
  InboxOutlined,
  MinusOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Button, Card, Progress, Skeleton, Typography } from "antd";
import { Link } from "react-router";

import { getErrorMessage } from "@/api/errors";
import { HistoryButton } from "@/components/AuditTrail";
import { PhotosButton } from "@/components/DocumentPhotos";
import { PrintButton } from "@/components/PrintButton";
import StatusTag from "@/components/StatusTag";
import { ACCENTS, type Accent } from "@/theme";
import { useCountUp } from "@/theme/motion";

export { ACCENTS, type Accent };

/** Responsive column counts for Descriptions on detail pages: one column on phones, three on desktops */
export const DESC_COLUMNS = { xs: 1, sm: 2, lg: 3 } as const;

/** Sticky table header that stays under the top bar while the page scrolls */
export const STICKY_HEADER = { offsetHeader: 56 } as const;

/** Table locale with a one-line empty message, for small related-record tables inside a card */
export const emptyLocale = (text: string) => ({ emptyText: <div className="wms-table-empty">{text}</div> });

export const formatQty = (v: number | null | undefined) =>
  v === null || v === undefined ? "" : v.toLocaleString(undefined, { maximumFractionDigits: 4 });

export function PageHeader({
  title,
  description,
  extra,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
  /** Small line above the title, e.g. the navigation group */
  eyebrow?: ReactNode;
}) {
  return (
    <div className="wms-page-header">
      <div style={{ minWidth: 0 }}>
        {eyebrow && <div className="wms-page-eyebrow">{eyebrow}</div>}
        <Typography.Title level={1} className="wms-page-title">
          {title}
        </Typography.Title>
        {description && (
          <Typography.Paragraph className="wms-page-desc" style={{ marginBottom: 0 }}>
            {description}
          </Typography.Paragraph>
        )}
      </div>
      {extra && <div className="wms-toolbar-group">{extra}</div>}
    </div>
  );
}

/** Link back to the list from a sub-page (new / edit / details) */
export function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="wms-backlink">
      <ArrowLeftOutlined style={{ fontSize: 12 }} />
      {label}
    </Link>
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

/** A number that counts up to its value when it first shows and when it changes */
export function AnimatedNumber({ value }: { value: number }) {
  const shown = useCountUp(value);
  return <>{fmt(Number.isInteger(value) ? Math.round(shown) : shown)}</>;
}

export function StatCard({
  label,
  value,
  icon,
  accent = "indigo",
  hint,
  to,
  testId,
  alert,
}: {
  label: string;
  value: number | string;
  icon?: ReactNode;
  accent?: Accent;
  hint?: ReactNode;
  to?: string;
  testId?: string;
  /** Needs attention: adds an accent bar (the hint should say why) */
  alert?: boolean;
}) {
  const a = ACCENTS[accent];
  const body = (
    <>
      <div className="wms-stat-top">
        <span className="wms-stat-label">{label}</span>
        {icon && (
          <span className="wms-stat-icon" style={{ color: a.fg, background: a.bg }} aria-hidden>
            {icon}
          </span>
        )}
      </div>
      <div className="wms-stat-value">{typeof value === "number" ? <AnimatedNumber value={value} /> : value}</div>
      {(hint || to) && (
        <div className="wms-stat-hint">
          {hint}
          {to && <ArrowRightOutlined className="wms-stat-arrow" aria-hidden />}
        </div>
      )}
    </>
  );
  const style = { "--wms-stat-accent": a.fg } as CSSProperties;
  const className = `wms-stat${alert ? " wms-stat-alert" : ""}`;
  return to ? (
    <Link to={to} className={className} style={style} data-testid={testId}>
      {body}
    </Link>
  ) : (
    <div className={className} style={style} data-testid={testId}>
      {body}
    </div>
  );
}

/** One headline number inside a KpiStrip */
export function Kpi({
  label,
  value,
  hint,
  to,
  icon,
  testId,
}: {
  label: string;
  value: number;
  hint?: ReactNode;
  to?: string;
  icon?: ReactNode;
  testId?: string;
}) {
  const body = (
    <>
      <div className="wms-kpi-label">
        {icon}
        {label}
      </div>
      <div className="wms-kpi-value"><AnimatedNumber value={value} /></div>
      {hint && <div className="wms-kpi-hint">{hint}</div>}
    </>
  );
  return to ? (
    <Link to={to} className="wms-kpi" data-testid={testId}>
      {body}
    </Link>
  ) : (
    <div className="wms-kpi" data-testid={testId}>
      {body}
    </div>
  );
}

export function KpiStrip({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <section className="wms-kpi-strip" aria-label={label}>
      {children}
    </section>
  );
}

export function SectionTitle({ title, extra }: { title: ReactNode; extra?: ReactNode }) {
  return (
    <div className="wms-section-title">
      <h3>{title}</h3>
      {extra && (typeof extra === "string" ? <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>{extra}</Typography.Text> : extra)}
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  hint,
  action,
  icon = <InboxOutlined />,
}: {
  title?: string;
  hint?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="wms-empty">
      <div className="wms-empty-icon" aria-hidden>
        {icon}
      </div>
      <div className="wms-empty-title">{title}</div>
      {hint && <div className="wms-empty-hint">{hint}</div>}
      {action && <div className="wms-empty-action">{action}</div>}
    </div>
  );
}

/** A request failed: say what went wrong and offer a retry */
export function ErrorState({
  title = "Could not load this page",
  error,
  onRetry,
  back,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
  /** Where "Back" goes, e.g. the list */
  back?: { to: string; label: string };
}) {
  return (
    <div className="wms-state-card wms-error" role="alert">
      <EmptyState
        icon={<WarningOutlined />}
        title={title}
        hint={error ? getErrorMessage(error) : "Check your connection and try again."}
        action={
          <div style={{ display: "inline-flex", gap: 8 }}>
            {onRetry && (
              <Button icon={<ReloadOutlined />} onClick={onRetry}>
                Try again
              </Button>
            )}
            {back && (
              <Link to={back.to}>
                <Button type="text">{back.label}</Button>
              </Link>
            )}
          </div>
        }
      />
    </div>
  );
}

/**
 * Placeholder while a document loads, shaped like a detail page (header card + lines card).
 * Only shown after a short delay: fast loads never flash a skeleton.
 */
export function DetailSkeleton({ rows = 5 }: { rows?: number }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 120);
    return () => window.clearTimeout(timer);
  }, []);
  if (!visible) return <div aria-busy="true" style={{ minHeight: 240 }} />;
  return (
    <div style={{ display: "grid", gap: 16 }} aria-busy="true" aria-label="Loading">
      <Card>
        <Skeleton active title={{ width: 220 }} paragraph={{ rows: 2, width: ["60%", "40%"] }} />
      </Card>
      <Card>
        <Skeleton active title={false} paragraph={{ rows, width: "100%" }} />
      </Card>
    </div>
  );
}

/** Header of a document detail card: document type, number, status and (with historyOf) the change history */
export function DocTitle({ label, no, status, historyOf }: { label: string; no: string; status?: string; historyOf?: string }) {
  return (
    <div className="wms-doc-title">
      <div style={{ lineHeight: 1.25, minWidth: 0 }}>
        <div className="wms-doc-kind">{label}</div>
        <div className="wms-mono wms-doc-no">{no}</div>
      </div>
      {status && <StatusTag status={status} />}
      {historyOf && <HistoryButton entityId={historyOf} title={`${label} ${no}`} />}
      {historyOf && <PhotosButton documentId={historyOf} title={`${label} ${no}`} />}
      {historyOf && <PrintButton documentId={historyOf} />}
    </div>
  );
}

/** Sticky action bar at the bottom of a create/edit form; the primary action (first child) sits on the far right */
export function FormFooter({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="wms-form-footer">
      {children}
      {note && <span className="wms-form-footer-note">{note}</span>}
    </div>
  );
}

/** A titled group of fields inside a form */
export function FormSection({ title, description, children }: { title: ReactNode; description?: ReactNode; children: ReactNode }) {
  return (
    <section className="wms-form-section">
      <h3 className="wms-form-section-title">{title}</h3>
      {description ? <p className="wms-form-section-desc">{description}</p> : <div style={{ height: 10 }} />}
      {children}
    </section>
  );
}

/**
 * Warn before closing or reloading the tab while a form has unsaved input. Pass the result of onValuesChange tracking;
 * call the returned reset (or pass false) once the form is saved.
 */
export function useUnsavedChanges() {
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
  return {
    dirty,
    /** Spread on <Form>: marks the form dirty on the first edit */
    formProps: { onValuesChange: () => !dirty && setDirty(true) },
    reset: () => setDirty(false),
  };
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
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size / 4),
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

/** A colored label; the text always carries the meaning (dot optional), never the color alone */
export function Pill({
  tone = "slate",
  children,
  dot,
  icon,
  title,
}: {
  tone?: Accent;
  children: ReactNode;
  dot?: boolean;
  icon?: ReactNode;
  title?: string;
}) {
  const a = ACCENTS[tone];
  return (
    <span className={dot ? "wms-status" : "wms-pill"} style={{ color: a.fg, background: a.bg }} title={title}>
      {dot && <span className="wms-status-dot" />}
      {icon}
      {children}
    </span>
  );
}

/** "12 / 20" with a thin bar under it, for received/shipped against ordered */
export function QtyProgress({ done, total, label }: { done: number; total: number; label?: string }) {
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const complete = total > 0 && done >= total;
  return (
    <div className="wms-qty-progress" aria-label={`${label ?? "Progress"}: ${formatQty(done)} of ${formatQty(total)}`}>
      <div className="wms-qty-progress-text">
        <span>
          {formatQty(done)} <span style={{ color: "var(--ant-color-text-quaternary)" }}>/ {formatQty(total)}</span>
        </span>
        <span style={{ color: complete ? ACCENTS.green.fg : "var(--ant-color-text-tertiary)" }}>{percent}%</span>
      </div>
      <Progress
        percent={percent}
        showInfo={false}
        size={{ height: 4 }}
        strokeColor={complete ? "var(--wms-tone-green-fg)" : undefined}
      />
    </div>
  );
}

export interface WorkflowStep {
  key: string;
  label: string;
}

/**
 * Where a document is in its lifecycle. `current` is the index of the step the document is at; `stopped` marks it as
 * ended early (cancelled / closed short) with its own label instead of the remaining steps.
 */
export function WorkflowSteps({
  steps,
  current,
  stopped,
}: {
  steps: WorkflowStep[];
  current: number;
  stopped?: { label: string };
}) {
  const shown = stopped ? [...steps.slice(0, current + 1), { key: "stopped", label: stopped.label }] : steps;
  return (
    <ol className="wms-steps" aria-label="Progress" style={{ listStyle: "none" }}>
      {shown.map((step, i) => {
        const isStop = !!stopped && i === shown.length - 1;
        const done = isStop ? true : stopped ? i <= current : i < current;
        const isCurrent = !stopped && i === current;
        // The final step of a completed flow counts as done, not "current"
        const finished = !stopped && i === current && current === steps.length - 1;
        const state = isStop ? "stopped" : finished || done ? "done" : isCurrent ? "current" : "todo";
        return (
          <li key={step.key} style={{ display: "contents" }}>
            {i > 0 && (
              <span
                className={`wms-step-line${done || isCurrent || finished ? " wms-step-line-done" : ""}`}
                style={{ "--i": i } as CSSProperties}
                aria-hidden
              />
            )}
            <span className={`wms-step wms-step-${state}`} style={{ "--i": i } as CSSProperties} aria-current={isCurrent && !finished ? "step" : undefined}>
              <span className="wms-step-marker" aria-hidden>
                {state === "done" ? <CheckOutlined /> : state === "stopped" ? <CloseOutlined /> : i + 1}
              </span>
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <span className="wms-brand-mark" style={{ width: size, height: size }}>
      <svg width={size * 0.58} height={size * 0.58} viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M3 9.5 12 4l9 5.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5Z" fill="rgba(255,255,255,0.14)" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" />
        <rect x="7" y="12" width="4" height="4" rx="0.8" fill="#fff" />
        <rect x="13" y="12" width="4" height="4" rx="0.8" fill="#fff" opacity="0.7" />
        <rect x="7" y="17" width="10" height="2" rx="0.8" fill="#fff" opacity="0.5" />
      </svg>
    </span>
  );
}
