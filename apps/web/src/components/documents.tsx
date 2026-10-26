import { useState, type KeyboardEvent } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Popconfirm, Select, Space, Table, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link, useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { STATUS_LABELS } from "@/constants/labels";

export const formatDateTime = (v: string | null) => (v ? new Date(v + "Z").toLocaleString() : "");

// 扫码枪每次扫描都会带一个回车，单据录入表单不能因为回车就提交，只能点按钮提交
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
      message.success("操作成功");
      queryClient.setQueryData([path, id], doc);
      // 收货过账会改变采购单状态和库存，相关缓存一起失效
      queryClient.invalidateQueries({ queryKey: [path] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
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
}: {
  label: string;
  confirm: string;
  onConfirm: () => void;
  loading: boolean;
  danger?: boolean;
  type?: "primary" | "default";
}) {
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
  extraParams,
}: {
  path: string;
  statuses: string[];
  columns: ColumnsType<DocumentSummary>;
  createLabel?: string;
  extraParams?: Record<string, string>;
}) {
  const navigate = useNavigate();
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

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space>
        {createLabel && (
          <Button type="primary" onClick={() => navigate(`/${path}/new`)}>
            {createLabel}
          </Button>
        )}
        <Select
          allowClear
          placeholder="按状态筛选"
          style={{ width: 160 }}
          value={status}
          onChange={setStatus}
          options={statuses.map((s) => ({ value: s, label: STATUS_LABELS[s]?.text ?? s }))}
        />
      </Space>
      <Table<DocumentSummary>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          {
            title: "单号",
            dataIndex: "doc_no",
            render: (v: string, r) => <Link to={`/${path}/${r.id}`}>{v}</Link>,
          },
          { title: "状态", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
          ...columns,
          { title: "创建时间", dataIndex: "created_at", render: formatDateTime },
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
        { title: "行号", dataIndex: "line_no", width: 60 },
        { title: "SKU", render: (_, l) => l.item.sku_code },
        { title: "商品", render: (_, l) => l.item.name },
        { title: "单位", render: (_, l) => l.uom.code, width: 70 },
        ...columns,
      ]}
    />
  );
}
