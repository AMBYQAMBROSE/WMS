import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Input, Popconfirm, Space, Table, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Link, useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import { usePreference } from "@/api/preferences";
import { printDocument } from "@/api/print";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import {
  ColumnSettings,
  EMPTY_PREFS,
  PeriodFilter,
  SavedViews,
  periodParams,
  useBatchRunner,
  type BatchAction,
  type ListFilters,
  type ListPrefs,
} from "@/components/ListTools";
import StatusTag from "@/components/StatusTag";
import { ErrorState, STICKY_HEADER, Toolbar, formatQty } from "@/components/ui";
import { STATUS_LABELS } from "@/constants/labels";

// Lists load the newest documents matching the filters, up to this many
const LIST_LIMIT = 200;

export const formatDateTime = (v: string | null) => (v ? dayjs(v + "Z").format("YYYY-MM-DD HH:mm") : "");

/** A right-aligned quantity column with thousands separators and tabular figures */
export function qtyColumn<T>(title: string, dataIndex: keyof T & string, extra: Partial<ColumnsType<T>[number]> = {}): ColumnsType<T>[number] {
  return { title, dataIndex, align: "right", render: (v: number | null) => formatQty(v), ...extra } as ColumnsType<T>[number];
}

// Barcode scanners send Enter after every scan, so document entry forms must not submit on Enter, only via the button
export function preventEnterSubmit(e: KeyboardEvent<HTMLFormElement>) {
  if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") e.preventDefault();
}

export function useDocument(path: string, id: string | undefined) {
  return useQuery({
    queryKey: [path, id],
    queryFn: async () => (await apiClient.get<Document>(`/${path}/${id}`)).data,
    enabled: !!id,
  });
}

interface Printable {
  id: string;
  doc_no: string;
}

export function useDocumentAction(
  path: string,
  id: string,
  options?: {
    /** Documents that posting created and that are printed right away too (a receipt's putaway sheet) */
    madeByPosting?: (doc: Document) => Promise<Printable[]>;
  },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: string) =>
      (await apiClient.post<Document>(`/${path}/${id}/${action}`)).data,
    onSuccess: async (doc, action) => {
      if (action === "post") {
        const made = options?.madeByPosting ? await options.madeByPosting(doc).catch(() => []) : [];
        // The paper copy is usually wanted right after posting (receipt for the supplier, DO for the driver). Offered
        // as a link rather than opened automatically: a tab opened without a click is blocked as a pop-up.
        const key = `posted-${doc.id}`;
        const link = (target: Printable, testId: string) => (
          <a
            key={target.id}
            data-testid={testId}
            style={{ marginLeft: 8 }}
            onClick={() => void printDocument(target.id)}
          >
            Print {target.doc_no}
          </a>
        );
        message.success({
          key,
          duration: made.length ? 15 : 8,
          content: (
            <span>
              Posted.
              {link(doc, "print-after-post")}
              {made.map((m) => link(m, "print-made-by-post"))}
            </span>
          ),
        });
      } else {
        message.success("Done");
      }
      queryClient.setQueryData([path, id], doc);
      // Posting receipts/picks/shipments changes PO and SO status and stock, so invalidate those caches too
      queryClient.invalidateQueries({ queryKey: [path] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
    onError: showError,
  });
}

export function ActionButton({
  label,
  confirm,
  onConfirm,
  loading,
  danger,
  type = "default",
  perm,
}: {
  label: string;
  confirm: string;
  onConfirm: () => void;
  loading: boolean;
  danger?: boolean;
  type?: "primary" | "default";
  /** Hide the button without this permission */
  perm?: string;
}) {
  const can = useCan();
  if (!can(perm)) return null;
  return (
    <Popconfirm title={confirm} onConfirm={onConfirm}>
      <Button type={type} danger={danger} loading={loading}>
        {label}
      </Button>
    </Popconfirm>
  );
}

export function DocumentListPage({
  path,
  statuses,
  columns,
  createLabel,
  createPerm,
  extraParams,
  batchActions = [],
}: {
  path: string;
  statuses: string[];
  columns: ColumnsType<DocumentSummary>;
  createLabel?: string;
  createPerm?: string;
  extraParams?: Record<string, string>;
  /** Actions that can run on several selected documents at once */
  batchActions?: BatchAction[];
}) {
  const navigate = useNavigate();
  const can = useCan();
  const queryClient = useQueryClient();
  const prefs = usePreference<ListPrefs>(`list:${path}`, EMPTY_PREFS);
  const [filters, setFilters] = useState<ListFilters>({});
  const [keywordInput, setKeywordInput] = useState("");
  const [selected, setSelected] = useState<DocumentSummary[]>([]);

  // Set once the user changes any filter: from then on the default view must not override them
  const touched = useRef(false);
  const applyFilters = (next: ListFilters) => {
    touched.current = true;
    setFilters(next);
    setKeywordInput(next.keyword ?? "");
    setSelected([]);
  };
  const patchFilters = (patch: Partial<ListFilters>) => applyFilters({ ...filters, ...patch });

  // Open with the user's default view, once their settings have loaded, unless they already started filtering
  const appliedDefault = useRef(false);
  useEffect(() => {
    if (!prefs.loaded || appliedDefault.current) return;
    appliedDefault.current = true;
    if (touched.current || keywordInput) return;
    const view = prefs.value.views.find((v) => v.name === prefs.value.defaultView);
    if (view) applyFilters(view.filters);
  }, [prefs.loaded, prefs.value]); // eslint-disable-line react-hooks/exhaustive-deps

  // Search on the server as the user types, after a short pause
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((filters.keyword ?? "") !== keywordInput.trim()) patchFilters({ keyword: keywordInput.trim() || undefined });
    }, 300);
    return () => clearTimeout(timer);
  }, [keywordInput]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: [path, "list", filters, extraParams],
    queryFn: async () =>
      (
        await apiClient.get<DocumentSummary[]>(`/${path}`, {
          params: { status: filters.status, keyword: filters.keyword, ...periodParams(filters), limit: LIST_LIMIT, ...extraParams },
        })
      ).data,
    placeholderData: (previous) => previous,
  });

  const allowedActions = batchActions.filter((a) => can(a.perm));
  const batch = useBatchRunner(path, () => {
    setSelected([]);
    ["stock", "reports", "purchase-orders", "sales-orders", path].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
  });

  const allColumns: ColumnsType<DocumentSummary> = [
    {
      title: "Document no.",
      dataIndex: "doc_no",
      render: (v: string, r) => <Link className="wms-mono" to={`/${path}/${r.id}`}>{v}</Link>,
    },
    { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
    ...columns,
    { title: "Created", dataIndex: "created_at", render: (v: string | null) => <Typography.Text type="secondary" style={{ whiteSpace: "nowrap" }}>{formatDateTime(v)}</Typography.Text> },
  ];
  // The document number always shows: it is how a row is recognised and opened
  const configurable = allColumns.slice(1).map((c) => String(c.title));
  const visibleColumns = allColumns.filter((c, i) => i === 0 || !prefs.value.hidden.includes(String(c.title)));

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <>
            <button type="button" className={`wms-chip${filters.status ? "" : " wms-chip-active"}`} onClick={() => patchFilters({ status: undefined })}>
              All
            </button>
            {statuses.map((s) => (
              <button
                type="button"
                key={s}
                className={`wms-chip${filters.status === s ? " wms-chip-active" : ""}`}
                onClick={() => patchFilters({ status: filters.status === s ? undefined : s })}
              >
                {STATUS_LABELS[s]?.text ?? s}
              </button>
            ))}
          </>
        }
        right={
          <>
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: "var(--ant-color-text-quaternary)" }} />}
              placeholder="Search number, partner, remark…"
              style={{ width: 240 }}
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
            />
            {createLabel && can(createPerm) && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/${path}/new`)}>
                {createLabel}
              </Button>
            )}
          </>
        }
      />
      <div className="wms-list-tools">
        <PeriodFilter value={filters} onChange={patchFilters} />
        <span style={{ flex: 1 }} />
        <SavedViews prefs={prefs.value} current={filters} onApply={applyFilters} onChange={prefs.save} disabled={!prefs.loaded} />
        <ColumnSettings
          columns={configurable}
          hidden={prefs.value.hidden}
          onChange={(hidden) => prefs.save({ ...prefs.value, hidden })}
          disabled={!prefs.loaded}
        />
      </div>
      {selected.length > 0 && allowedActions.length > 0 && (
        <div className="wms-batch-bar" role="region" aria-label="Batch actions">
          <span className="wms-batch-count">{selected.length} selected</span>
          {allowedActions.map((action) => {
            const eligible = selected.filter((d) => action.statuses.includes(d.status)).length;
            const skipped = selected.length - eligible;
            return (
              <Popconfirm
                key={action.key}
                title={`${action.label} ${eligible} document${eligible === 1 ? "" : "s"}?`}
                description={skipped ? `${skipped} selected ${skipped === 1 ? "is" : "are"} in another status and will be skipped.` : undefined}
                onConfirm={() => void batch.run(action, selected)}
                disabled={!eligible}
              >
                <Button danger={action.danger} disabled={!eligible || batch.running}>
                  {action.label} ({eligible})
                </Button>
              </Popconfirm>
            );
          })}
          <Button type="link" onClick={() => setSelected([])}>
            Clear selection
          </Button>
        </div>
      )}
      {error && !data ? (
        <ErrorState title="Could not load the list" error={error} onRetry={() => refetch()} />
      ) : (
      <Table<DocumentSummary>
        rowKey="id"
        loading={isLoading}
        className={isFetching && !isLoading ? "wms-refreshing" : undefined}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        rowClassName="wms-row-link"
        dataSource={data}
        rowSelection={
          allowedActions.length
            ? {
                selectedRowKeys: selected.map((d) => d.id),
                onChange: (_, rows) => setSelected(rows),
                preserveSelectedRowKeys: true,
              }
            : undefined
        }
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) =>
            `${total.toLocaleString()} document${total === 1 ? "" : "s"}${total === LIST_LIMIT ? ` (latest ${LIST_LIMIT}; narrow the filters to see older ones)` : ""}`,
        }}
        onRow={(r) => ({
          onClick: (e) => {
            // Clicking anywhere on the row opens the document, except on links, buttons and the selection checkbox
            if (!(e.target as HTMLElement).closest("a,button,.ant-table-selection-column")) navigate(`/${path}/${r.id}`);
          },
        })}
        columns={visibleColumns}
      />
      )}
      {batch.modal}
    </Space>
  );
}

export function DocumentLinesTable({
  lines,
  columns,
}: {
  lines: DocumentLine[];
  columns: ColumnsType<DocumentLine>;
}) {
  return (
    <Table<DocumentLine>
      rowKey="id"
      size="small"
      pagination={false}
      dataSource={lines}
      scroll={{ x: "max-content" }}
      columns={[
        { title: "#", dataIndex: "line_no", width: 48, render: (v: number) => <Typography.Text type="secondary" className="wms-num">{v}</Typography.Text> },
        { title: "SKU", render: (_, l) => <span className="wms-mono">{l.item.sku_code}</span> },
        { title: "Item", render: (_, l) => l.item.name },
        { title: "Unit", render: (_, l) => l.uom.code, width: 70 },
        ...columns,
      ]}
    />
  );
}
