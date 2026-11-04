import { useState, type KeyboardEvent } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Input, Popconfirm, Space, Table, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Link, useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { Toolbar } from "@/components/ui";
import { STATUS_LABELS } from "@/constants/labels";

export const formatDateTime = (v: string | null) => (v ? dayjs(v + "Z").format("YYYY-MM-DD HH:mm") : "");

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

export function useDocumentAction(path: string, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: string) =>
      (await apiClient.post<Document>(`/${path}/${id}/${action}`)).data,
    onSuccess: (doc) => {
      message.success("Done");
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
}: {
  path: string;
  statuses: string[];
  columns: ColumnsType<DocumentSummary>;
  createLabel?: string;
  createPerm?: string;
  extraParams?: Record<string, string>;
}) {
  const navigate = useNavigate();
  const can = useCan();
  const [status, setStatus] = useState<string | undefined>();
  const { data, isLoading } = useQuery({
    queryKey: [path, "list", status, extraParams],
    queryFn: async () =>
      (
        await apiClient.get<DocumentSummary[]>(`/${path}`, {
          params: { status, limit: 200, ...extraParams },
        })
      ).data,
  });

  const [keyword, setKeyword] = useState("");
  const needle = keyword.trim().toLowerCase();
  const rows = needle
    ? data?.filter((r) =>
        [r.doc_no, r.partner?.name, r.partner?.code, r.ref_document?.doc_no, r.remark]
          .some((v) => v?.toLowerCase().includes(needle)),
      )
    : data;

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <>
            <button type="button" className={`wms-chip${status ? "" : " wms-chip-active"}`} onClick={() => setStatus(undefined)}>
              All
            </button>
            {statuses.map((s) => (
              <button
                type="button"
                key={s}
                className={`wms-chip${status === s ? " wms-chip-active" : ""}`}
                onClick={() => setStatus(status === s ? undefined : s)}
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
              placeholder="Search number, partner…"
              style={{ width: 240 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            {createLabel && can(createPerm) && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/${path}/new`)}>
                {createLabel}
              </Button>
            )}
          </>
        }
      />
      <Table<DocumentSummary>
        rowKey="id"
        loading={isLoading}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total.toLocaleString()} documents` }}
        onRow={(r) => ({
          onClick: (e) => {
            // Clicking anywhere on the row opens the document, except on links/buttons inside it
            if (!(e.target as HTMLElement).closest("a,button")) navigate(`/${path}/${r.id}`);
          },
          style: { cursor: "pointer" },
        })}
        columns={[
          {
            title: "Document no.",
            dataIndex: "doc_no",
            render: (v: string, r) => <Link className="wms-mono" to={`/${path}/${r.id}`}>{v}</Link>,
          },
          { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
          ...columns,
          { title: "Created", dataIndex: "created_at", render: (v: string | null) => <Typography.Text type="secondary">{formatDateTime(v)}</Typography.Text> },
        ]}
      />
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
      columns={[
        { title: "Line", dataIndex: "line_no", width: 60 },
        { title: "SKU", render: (_, l) => <span className="wms-mono">{l.item.sku_code}</span> },
        { title: "Item", render: (_, l) => l.item.name },
        { title: "Unit", render: (_, l) => l.uom.code, width: 70 },
        ...columns,
      ]}
    />
  );
}
