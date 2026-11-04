/**
 * Building blocks for list pages: saved views (named filter sets), column visibility and batch actions.
 * Views and columns are stored per user on the server (usePreference), so they follow the user to any PC.
 */
import { useRef, useState } from "react";

import {
  CheckOutlined,
  DeleteOutlined,
  DownOutlined,
  EyeOutlined,
  SaveOutlined,
  StarFilled,
  StarOutlined,
} from "@ant-design/icons";
import { Button, Checkbox, DatePicker, Dropdown, Input, Modal, Popover, Progress, Select, Space, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";

import type { ColumnsType } from "antd/es/table";

import { apiClient } from "@/api/client";
import { getErrorMessage } from "@/api/errors";
import { usePreference } from "@/api/preferences";

// ---------------------------------------------------------------- filters

export type Period = "any" | "today" | "7d" | "30d" | "custom";

export interface ListFilters {
  status?: string;
  keyword?: string;
  /** Relative periods stay relative in a saved view: "Last 7 days" means the last 7 days whenever it is opened */
  period?: Period;
  /** Only for period "custom": YYYY-MM-DD, inclusive */
  from?: string;
  to?: string;
}

export function periodParams(f: ListFilters): { created_from?: string; created_to?: string } {
  const today = dayjs();
  const day = (d: Dayjs) => d.format("YYYY-MM-DD");
  switch (f.period) {
    case "today":
      return { created_from: day(today) };
    case "7d":
      return { created_from: day(today.subtract(6, "day")) };
    case "30d":
      return { created_from: day(today.subtract(29, "day")) };
    case "custom":
      return { created_from: f.from, created_to: f.to };
    default:
      return {};
  }
}

export function PeriodFilter({ value, onChange }: { value: ListFilters; onChange: (patch: Partial<ListFilters>) => void }) {
  const period = value.period ?? "any";
  return (
    <Space.Compact>
      <Select<Period>
        value={period}
        style={{ width: 140 }}
        onChange={(p) => onChange({ period: p, from: undefined, to: undefined })}
        options={[
          { value: "any", label: "Any time" },
          { value: "today", label: "Created today" },
          { value: "7d", label: "Last 7 days" },
          { value: "30d", label: "Last 30 days" },
          { value: "custom", label: "Custom…" },
        ]}
      />
      {period === "custom" && (
        <DatePicker.RangePicker
          style={{ width: 240 }}
          value={value.from && value.to ? [dayjs(value.from), dayjs(value.to)] : null}
          onChange={(r) => onChange({ from: r?.[0]?.format("YYYY-MM-DD"), to: r?.[1]?.format("YYYY-MM-DD") })}
        />
      )}
    </Space.Compact>
  );
}

// ---------------------------------------------------------------- saved views and columns

export interface SavedView {
  name: string;
  filters: ListFilters;
}

export interface ListPrefs {
  views: SavedView[];
  /** Applied when the list opens */
  defaultView?: string;
  /** Titles of hidden columns */
  hidden: string[];
}

export const EMPTY_PREFS: ListPrefs = { views: [], hidden: [] };

const sameFilters = (a: ListFilters, b: ListFilters) =>
  (a.status ?? "") === (b.status ?? "") &&
  (a.keyword ?? "") === (b.keyword ?? "") &&
  (a.period ?? "any") === (b.period ?? "any") &&
  (a.from ?? "") === (b.from ?? "") &&
  (a.to ?? "") === (b.to ?? "");

export function SavedViews({
  prefs,
  current,
  onApply,
  onChange,
  disabled,
}: {
  prefs: ListPrefs;
  current: ListFilters;
  onApply: (filters: ListFilters) => void;
  onChange: (prefs: ListPrefs) => void;
  /** Until the saved settings have loaded */
  disabled?: boolean;
}) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const active = prefs.views.find((v) => sameFilters(v.filters, current));

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    // Same name: the view is updated in place
    const views = [...prefs.views.filter((v) => v.name !== trimmed), { name: trimmed, filters: current }];
    onChange({ ...prefs, views });
    setNaming(false);
  };

  const items = [
    ...prefs.views.map((v) => ({
      key: `view:${v.name}`,
      label: (
        <div className="wms-view-item">
          <span className="wms-view-check">{active?.name === v.name && <CheckOutlined />}</span>
          <span style={{ flex: 1 }}>{v.name}</span>
          <Button
            type="text"
            size="small"
            aria-label={prefs.defaultView === v.name ? `Stop opening ${v.name} by default` : `Open ${v.name} by default`}
            title={prefs.defaultView === v.name ? "Opens by default" : "Open by default"}
            icon={prefs.defaultView === v.name ? <StarFilled style={{ color: "var(--ant-color-warning)" }} /> : <StarOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              onChange({ ...prefs, defaultView: prefs.defaultView === v.name ? undefined : v.name });
            }}
          />
          <Button
            type="text"
            size="small"
            aria-label={`Delete view ${v.name}`}
            icon={<DeleteOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              onChange({
                ...prefs,
                views: prefs.views.filter((x) => x.name !== v.name),
                defaultView: prefs.defaultView === v.name ? undefined : prefs.defaultView,
              });
            }}
          />
        </div>
      ),
      onClick: () => onApply(v.filters),
    })),
    ...(prefs.views.length ? [{ type: "divider" as const }] : []),
    {
      key: "save",
      icon: <SaveOutlined />,
      label: "Save current filters as a view…",
      onClick: () => {
        setName(active?.name ?? "");
        setNaming(true);
      },
    },
  ];

  return (
    <>
      <Dropdown menu={{ items }} trigger={["click"]} disabled={disabled}>
        <Button disabled={disabled}>
          {active ? active.name : "Views"} <DownOutlined />
        </Button>
      </Dropdown>
      <Modal title="Save view" open={naming} onOk={save} onCancel={() => setNaming(false)} okText="Save" destroyOnHidden>
        <Typography.Paragraph type="secondary">
          Saves the current status, search and period. Saved views are yours: they follow you to any PC.
        </Typography.Paragraph>
        <Input autoFocus maxLength={40} placeholder="e.g. Drafts this week" value={name} onChange={(e) => setName(e.target.value)} onPressEnter={save} />
      </Modal>
    </>
  );
}

export function ColumnSettings({
  columns,
  hidden,
  onChange,
  disabled,
}: {
  columns: string[];
  hidden: string[];
  onChange: (hidden: string[]) => void;
  /** Until the saved settings have loaded */
  disabled?: boolean;
}) {
  const content = (
    <div style={{ display: "grid", gap: 6, minWidth: 200 }}>
      {columns.map((title) => (
        <Checkbox
          key={title}
          checked={!hidden.includes(title)}
          onChange={(e) => onChange(e.target.checked ? hidden.filter((h) => h !== title) : [...hidden, title])}
        >
          {title}
        </Checkbox>
      ))}
      <Button size="small" type="link" style={{ justifySelf: "start", padding: 0 }} disabled={!hidden.length} onClick={() => onChange([])}>
        Show all
      </Button>
    </div>
  );
  return (
    <Popover content={content} title="Columns" trigger="click" placement="bottomRight">
      <Button icon={<EyeOutlined />} aria-label="Choose columns" disabled={disabled}>
        Columns{hidden.length ? ` (${columns.length - hidden.length}/${columns.length})` : ""}
      </Button>
    </Popover>
  );
}

// ---------------------------------------------------------------- batch actions

export interface BatchAction {
  /** Endpoint suffix: POST /{path}/{id}/{key} */
  key: string;
  label: string;
  perm: string;
  /** Statuses the action applies to; other selected documents are skipped */
  statuses: string[];
  danger?: boolean;
}

interface BatchTarget {
  id: string;
  doc_no: string;
  status: string;
}

interface BatchResult {
  doc_no: string;
  outcome: "done" | "skipped" | "failed";
  detail?: string;
}

/**
 * Runs an action on documents one at a time through the normal endpoints: every document gets the same permission and
 * business-rule checks as from its detail page, in its own transaction, so one failure does not undo the others.
 */
export function useBatchRunner(path: string, onFinished: () => void) {
  const [state, setState] = useState<{ action: BatchAction; done: number; total: number; results: BatchResult[]; running: boolean } | null>(null);
  const stopRequested = useRef(false);

  const run = async (action: BatchAction, targets: BatchTarget[]) => {
    stopRequested.current = false;
    const results: BatchResult[] = [];
    setState({ action, done: 0, total: targets.length, results, running: true });
    for (const [i, t] of targets.entries()) {
      if (stopRequested.current) {
        results.push({ doc_no: t.doc_no, outcome: "skipped", detail: "Stopped before this document" });
      } else if (!action.statuses.includes(t.status)) {
        results.push({ doc_no: t.doc_no, outcome: "skipped", detail: `Status is ${t.status}` });
      } else {
        try {
          await apiClient.post(`/${path}/${t.id}/${action.key}`);
          results.push({ doc_no: t.doc_no, outcome: "done" });
        } catch (error) {
          results.push({ doc_no: t.doc_no, outcome: "failed", detail: getErrorMessage(error) });
        }
      }
      setState({ action, done: i + 1, total: targets.length, results: [...results], running: true });
    }
    setState((s) => s && { ...s, running: false });
    onFinished();
  };

  const counts = (state?.results ?? []).reduce(
    (acc, r) => ({ ...acc, [r.outcome]: acc[r.outcome] + 1 }),
    { done: 0, skipped: 0, failed: 0 },
  );
  const problems = state?.results.filter((r) => r.outcome !== "done") ?? [];

  const modal = state && (
    <Modal
      open
      title={`${state.action.label}: ${state.running ? "working…" : "finished"}`}
      closable={!state.running}
      maskClosable={false}
      onCancel={() => setState(null)}
      footer={
        state.running ? (
          <Button onClick={() => (stopRequested.current = true)}>Stop after the current document</Button>
        ) : (
          <Button type="primary" onClick={() => setState(null)}>
            Close
          </Button>
        )
      }
    >
      <Progress percent={Math.round((state.done / state.total) * 100)} status={counts.failed ? "exception" : state.running ? "active" : "success"} />
      <Typography.Paragraph style={{ marginTop: 8 }} data-testid="batch-summary">
        {counts.done} done · {counts.skipped} skipped · {counts.failed} failed · of {state.total}
      </Typography.Paragraph>
      {problems.length > 0 && (
        <div style={{ maxHeight: 240, overflowY: "auto", display: "grid", gap: 6 }}>
          {problems.map((r) => (
            <div key={r.doc_no}>
              <Typography.Text className="wms-mono" strong>
                {r.doc_no}
              </Typography.Text>{" "}
              <Typography.Text type={r.outcome === "failed" ? "danger" : "secondary"}>
                {r.outcome === "failed" ? "Failed" : "Skipped"}: {r.detail}
              </Typography.Text>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );

  return { run, running: !!state?.running, modal };
}

/** Post and cancel, for documents that are drafted and then posted (receipts, putaways, moves, shipments, ...) */
export function postAndCancel(permPrefix: string, draft = "DRAFT"): BatchAction[] {
  return [
    { key: "post", label: "Post", perm: `${permPrefix}.post`, statuses: [draft] },
    { key: "cancel", label: "Cancel", perm: `${permPrefix}.cancel`, statuses: [draft], danger: true },
  ];
}

/** Column visibility for a plain list table, saved per user; the first column always shows */
export function useColumnPrefs<T>(listKey: string, columns: ColumnsType<T>) {
  const prefs = usePreference<ListPrefs>(`list:${listKey}`, EMPTY_PREFS);
  const hidden = prefs.value.hidden;
  return {
    columns: columns.filter((c, i) => i === 0 || !hidden.includes(String(c.title))),
    settings: (
      <ColumnSettings
        columns={columns.slice(1).map((c) => String(c.title))}
        hidden={hidden}
        onChange={(next) => prefs.save({ ...prefs.value, hidden: next })}
        disabled={!prefs.loaded}
      />
    ),
  };
}
