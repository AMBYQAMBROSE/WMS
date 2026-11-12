import { useState } from "react";

import { DownloadOutlined, FileExcelOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Modal, Result, Space, Table, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { ImportResult } from "@/api/types";

/** What an import kind is called and needs; the full list comes from GET /imports */
export interface ImportKindInfo {
  key: string;
  name: string;
}

/** Order imports create one document per order; these are the document routes */
const ORDER_PATHS: Record<string, string> = {
  purchase_orders: "purchase-orders",
  sales_orders: "sales-orders",
};

// Caches to refresh after an import
const AFFECTED: Record<string, string[]> = {
  items: ["items"],
  locations: ["locations"],
  partners: ["business-partners"],
  opening_stock: ["stock", "adjustments"],
  purchase_orders: ["purchase-orders"],
  sales_orders: ["sales-orders"],
};

async function download(kind: ImportKindInfo) {
  try {
    const res = await apiClient.get<Blob>(`/imports/${kind.key}/template`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Import template - ${kind.name}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    showError(error);
  }
}

function summary(kind: ImportKindInfo, r: ImportResult) {
  if (ORDER_PATHS[kind.key]) return `${r.total} rows make ${r.created} ${kind.name.toLowerCase()}, created as drafts`;
  if (kind.key === "opening_stock") return `${r.total} rows, ${r.created} stock records after merging`;
  return `${r.total} rows, ${r.created} to create and ${r.updated} to update`;
}

/** Steps 2-3 of an import: download template -> choose file -> validate -> import. Nothing is written unless every row is valid. */
export function ImportRunner({ kind, onDone }: { kind: ImportKindInfo; onDone?: (result: ImportResult) => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<UploadFile & { originFileObj?: File }>();
  const [result, setResult] = useState<ImportResult>();
  const orderPath = ORDER_PATHS[kind.key];

  const run = useMutation({
    mutationFn: async (commit: boolean) => {
      const body = new FormData();
      body.append("file", file!.originFileObj as File);
      return (await apiClient.post<ImportResult>(`/imports/${kind.key}`, body, { params: { commit } })).data;
    },
    onSuccess: (r) => {
      setResult(r);
      if (r.committed) {
        message.success("Import complete");
        AFFECTED[r.kind]?.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
        onDone?.(r);
      }
    },
    onError: showError,
  });

  const reset = () => {
    setFile(undefined);
    setResult(undefined);
  };

  const orders = orderPath && result && result.error_count === 0 && (result.documents?.length ?? 0) > 0 && (
    <Table
      size="small"
      rowKey={(d, i) => `${d.ref ?? ""}-${i}`}
      dataSource={result.documents}
      pagination={{ pageSize: 10, hideOnSinglePage: true }}
      columns={[
        {
          title: "Order",
          render: (_, d) =>
            d.document_id ? <Link className="wms-mono" to={`/${orderPath}/${d.document_id}`}>{d.document_no}</Link> : <Typography.Text type="secondary">To be created</Typography.Text>,
        },
        { title: "Order ref", dataIndex: "ref", render: (v: string | null) => v || <span className="wms-empty-value">—</span> },
        { title: kind.key === "purchase_orders" ? "Supplier" : "Customer", dataIndex: "partner" },
        { title: "Lines", dataIndex: "lines", align: "right" },
      ]}
    />
  );

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Card size="small" title="Prepare the file">
        <Space wrap align="start">
          <Button icon={<DownloadOutlined />} onClick={() => download(kind)}>
            Download {kind.name.toLowerCase()} template
          </Button>
          <Upload
            accept=".xlsx,.csv"
            maxCount={1}
            fileList={file ? [file] : []}
            beforeUpload={() => false}
            onChange={({ fileList }) => {
              setFile(fileList[0]);
              setResult(undefined);
            }}
          >
            <Button icon={<UploadOutlined />}>Choose file (.xlsx / .csv)</Button>
          </Upload>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          Row 1 of the template is the header and columns marked * are required; row 2 is an example, delete it before importing. The Notes sheet explains every column. At most 100,000 rows / 20MB per file.
        </Typography.Paragraph>
      </Card>

      {file && (
        <Card size="small" title="Validate and import">
          <Space orientation="vertical" style={{ width: "100%" }}>
            <Space>
              <Button onClick={() => run.mutate(false)} loading={run.isPending && run.variables === false}>
                Validate
              </Button>
              <Button
                type="primary"
                disabled={!result || result.error_count > 0 || result.committed}
                onClick={() => run.mutate(true)}
                loading={run.isPending && run.variables === true}
              >
                Import
              </Button>
            </Space>

            {result && !result.committed && result.error_count === 0 && (
              <>
                <Alert type="success" showIcon title={`Validation passed: ${summary(kind, result)}. Click Import to apply`} />
                {orders}
              </>
            )}
            {result && result.error_count > 0 && (
              <>
                <Alert
                  type="error"
                  showIcon
                  title={`${result.error_count} errors. Fix the file, choose it again and validate (nothing is imported unless everything is correct)`}
                />
                <Table
                  size="small"
                  rowKey={(e) => `${e.row}-${e.column}-${e.message}`}
                  dataSource={result.errors}
                  pagination={{ pageSize: 20, hideOnSinglePage: true }}
                  columns={[
                    { title: "Row", dataIndex: "row", width: 80, render: (v: number) => (v ? v : "-") },
                    { title: "Column", dataIndex: "column", width: 160 },
                    { title: "Problem", dataIndex: "message" },
                  ]}
                  footer={() => (result.error_count > result.errors.length ? `Showing the first ${result.errors.length}` : null)}
                />
              </>
            )}
            {result?.committed && (
              <Result
                status="success"
                title="Import complete"
                subTitle={
                  orderPath ? (
                    `Created ${result.created} draft ${kind.name.toLowerCase()}. Review and confirm them in the list.`
                  ) : result.document_no ? (
                    <>
                      Created and posted stock adjustment <Link to={`/adjustments/${result.document_id}`}>{result.document_no}</Link> ({result.created} stock records)
                    </>
                  ) : (
                    `${result.created} created, ${result.updated} updated`
                  )
                }
                extra={<Button onClick={reset}>Import more</Button>}
              />
            )}
            {result?.committed && orders}
          </Space>
        </Card>
      )}
    </Space>
  );
}

/** "Import from Excel" on a document list: the same import flow in a dialog */
export function ImportButton({ kind, perm }: { kind: ImportKindInfo; perm: string }) {
  const can = useCan();
  const [open, setOpen] = useState(false);
  if (!can(perm)) return null;
  return (
    <>
      <Button icon={<FileExcelOutlined />} onClick={() => setOpen(true)}>
        Import from Excel
      </Button>
      <Modal open={open} title={`Import ${kind.name.toLowerCase()} from Excel`} onCancel={() => setOpen(false)} footer={null} width={760} destroyOnHidden>
        <Typography.Paragraph type="secondary">
          One row per order line. Rows with the same order ref become one order; without a ref, rows for the same partner, date and remark are grouped. Every order is created as a draft.
        </Typography.Paragraph>
        <ImportRunner kind={kind} />
      </Modal>
    </>
  );
}
