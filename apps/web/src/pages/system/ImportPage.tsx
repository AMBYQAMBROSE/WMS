import { useState } from "react";

import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Radio, Result, Space, Steps, Table, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";

interface ImportKind {
  key: string;
  name: string;
  permissions: string[];
  allowed: boolean;
}

interface ImportResult {
  kind: string;
  total: number;
  created: number;
  updated: number;
  error_count: number;
  errors: { row: number; column: string; message: string }[];
  warnings: string[];
  committed: boolean;
  document_id: string | null;
  document_no: string | null;
}

const DESCRIPTIONS: Record<string, string> = {
  items: "Matched by SKU code: existing items are updated, new ones created. The base unit of an existing item cannot change.",
  locations: "Matched by location code: existing locations are updated, new ones created. Parents may be in the same file (any order).",
  partners: "Matched by code: existing partners are updated, new ones created. Type is Customer / Supplier / Both.",
  opening_stock: "Result of the pre-go-live stock count. Importing creates one posted stock adjustment (reason: opening stock). Import items and locations first.",
};

// Caches to refresh after an import
const AFFECTED: Record<string, string[]> = {
  items: ["items"],
  locations: ["locations"],
  partners: ["business-partners"],
  opening_stock: ["stock", "adjustments"],
};

async function download(kind: ImportKind) {
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

/** Go-live data import: download template -> fill in -> validate -> import */
export default function ImportPage() {
  const queryClient = useQueryClient();
  const { data: kinds } = useQuery({
    queryKey: ["imports"],
    queryFn: async () => (await apiClient.get<ImportKind[]>("/imports")).data,
  });
  const [kindKey, setKindKey] = useState<string>();
  const [file, setFile] = useState<UploadFile & { originFileObj?: File }>();
  const [result, setResult] = useState<ImportResult>();
  const kind = kinds?.find((k) => k.key === kindKey);

  const run = useMutation({
    mutationFn: async (commit: boolean) => {
      const body = new FormData();
      body.append("file", file!.originFileObj as File);
      return (await apiClient.post<ImportResult>(`/imports/${kindKey}`, body, { params: { commit } })).data;
    },
    onSuccess: (r) => {
      setResult(r);
      if (r.committed) {
        message.success("Import complete");
        AFFECTED[r.kind]?.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      }
    },
    onError: showError,
  });

  const reset = () => {
    setFile(undefined);
    setResult(undefined);
  };
  const step = !kind ? 0 : !file ? 1 : !result || result.error_count ? 2 : result.committed ? 4 : 3;

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Steps
        size="small"
        current={step}
        items={[{ title: "Choose type" }, { title: "Download and fill template" }, { title: "Upload and validate" }, { title: "Import" }, { title: "Done" }]}
      />
      <Card size="small" title="1. What to import">
        <Radio.Group
          value={kindKey}
          onChange={(e) => {
            setKindKey(e.target.value);
            reset();
          }}
          optionType="button"
          buttonStyle="solid"
          options={(kinds ?? []).map((k) => ({ value: k.key, label: k.name, disabled: !k.allowed }))}
        />
        {kind && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            {DESCRIPTIONS[kind.key]}
          </Typography.Paragraph>
        )}
      </Card>

      {kind && (
        <Card size="small" title="2. Prepare the file">
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
            Row 1 of the template is the header and columns marked * are required; row 2 is an example, delete it before importing. At most 100,000 rows / 20MB per file.
          </Typography.Paragraph>
        </Card>
      )}

      {kind && file && (
        <Card size="small" title="3. Validate and import">
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
              <Alert
                type="success"
                showIcon
                title={
                  kind.key === "opening_stock"
                    ? `Validation passed: ${result.total} rows, ${result.created} stock records after merging. Click Import to apply`
                    : `Validation passed: ${result.total} rows, ${result.created} to create and ${result.updated} to update. Click Import to apply`
                }
              />
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
                  result.document_no ? (
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
          </Space>
        </Card>
      )}
    </Space>
  );
}
