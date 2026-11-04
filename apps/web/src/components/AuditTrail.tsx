import { useState, type ReactNode } from "react";

import { ArrowRightOutlined, HistoryOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Drawer, Empty, Spin, Tag, Timeline, Typography } from "antd";
import dayjs from "dayjs";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { AuditChange, AuditLog } from "@/api/types";
import { AUDIT_ACTION_LABELS, AUDIT_ENTITY_LABELS, DOC_TYPE_LABELS } from "@/constants/labels";

// No imports from ui/documents: DocTitle in ui.tsx renders HistoryButton, and that would make an import cycle

export const formatAuditTime = (v: string) => dayjs(v + "Z").format("YYYY-MM-DD HH:mm:ss");

/** qty_planned -> Qty planned, item_id -> Item, is_active -> Active */
export function fieldLabel(field: string) {
  const words = field.replace(/^is_/, "").replace(/_id$/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function formatValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return <Typography.Text type="secondary">empty</Typography.Text>;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : <Typography.Text type="secondary">none</Typography.Text>;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function entityTitle(log: AuditLog) {
  const type = AUDIT_ENTITY_LABELS[log.entity_type] ?? log.entity_type;
  if (log.entity_type === "document" && log.entity_label) {
    // Label is "<doc type> <doc no>"
    const [docType, docNo] = log.entity_label.split(" ");
    return `${DOC_TYPE_LABELS[docType] ?? docType} ${docNo ?? ""}`;
  }
  // Labels of document children already name their document: "PO20261104-0001 line 1"
  if (log.entity_type === "document_line" || log.entity_type === "count_entry") return log.entity_label ?? type;
  return log.entity_label ? `${type} ${log.entity_label}` : type;
}

export function ActionTag({ action }: { action: string }) {
  const label = AUDIT_ACTION_LABELS[action] ?? { text: action, color: "default" };
  return <Tag color={label.color}>{label.text}</Tag>;
}

/** Field-by-field old -> new; a create shows only new values and a hard delete only old ones */
export function AuditChanges({ changes, action }: { changes: AuditChange[]; action: string }) {
  if (!changes.length) return null;
  return (
    <div className="wms-audit-changes">
      {changes.map((c) => (
        <div key={c.field} className="wms-audit-change">
          <span className="wms-audit-field">{fieldLabel(c.field)}</span>
          <span>
            {action !== "CREATE" && <span className="wms-audit-old">{formatValue(c.old)}</span>}
            {action === "UPDATE" && <ArrowRightOutlined className="wms-audit-arrow" />}
            {action !== "DELETE" || c.new !== null ? <span className="wms-audit-new">{formatValue(c.new)}</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Actor({ log }: { log: AuditLog }) {
  return log.username ? <>{log.username}</> : <Typography.Text type="secondary">System</Typography.Text>;
}

/** History of one record; for a document it includes its lines, loading details and count entries */
export function AuditTimeline({ entityId }: { entityId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", "entity", entityId],
    queryFn: async () => (await apiClient.get<AuditLog[]>("/audit-logs", { params: { entity_id: entityId, limit: 500 } })).data,
  });
  if (isLoading) return <Spin />;
  if (!data?.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No recorded changes" />;
  return (
    <Timeline
      items={data.map((log) => ({
        key: log.id,
        color: (AUDIT_ACTION_LABELS[log.action] ?? { color: "gray" }).color,
        title: (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {formatAuditTime(log.occurred_at)} · <Actor log={log} />
          </Typography.Text>
        ),
        content: (
          <div>
            <div style={{ marginBottom: 4 }}>
              <ActionTag action={log.action} />
              <Typography.Text strong>{entityTitle(log)}</Typography.Text>
            </div>
            <AuditChanges changes={log.changes} action={log.action} />
          </div>
        ),
      }))}
    />
  );
}

/** "History" button for a record's detail page; hidden without the audit.read permission */
export function HistoryButton({ entityId, title = "History" }: { entityId: string; title?: string }) {
  const can = useCan();
  const [open, setOpen] = useState(false);
  if (!can("audit.read")) return null;
  return (
    <>
      <Button type="text" size="small" icon={<HistoryOutlined />} onClick={() => setOpen(true)}>
        History
      </Button>
      <Drawer open={open} onClose={() => setOpen(false)} title={title} size={560} destroyOnHidden>
        <AuditTimeline entityId={entityId} />
      </Drawer>
    </>
  );
}
