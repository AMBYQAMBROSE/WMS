import { useState } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, Form, InputNumber, Modal, Space, Tooltip, message } from "antd";
import { Link, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Document, DocumentLine } from "@/api/types";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, Pill, QtyProgress, formatQty } from "@/components/ui";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";
import { LocationSelect } from "@/components/selects";

const PERM_PREFIX = { putaways: "putaway", moves: "move" } as const;

/** A putaway sheet (made from a posted receipt) is worked line by line, usually on the PDA */
const isSheet = (doc: Document) => doc.status === "TO_PUT_AWAY" || doc.lines.some((l) => l.confirmed_at);

/** Putaway / move detail: posting moves the stock from the source to the target location */
export default function TransferDetail({ path, docLabel }: { path: "putaways" | "moves"; docLabel: string }) {
  const { id = "" } = useParams();
  const can = useCan();
  const { data: doc, isLoading, error, refetch } = useDocument(path, id);
  const action = useDocumentAction(path, id);
  const [putting, setPutting] = useState<DocumentLine | null>(null);

  if (isLoading) return <DetailSkeleton />;
  if (!doc) return <ErrorState title={`Could not load this ${docLabel.toLowerCase()}`} error={error} onRetry={() => refetch()} back={{ to: `/${path}`, label: "Back to the list" }} />;
  const run = (name: string) => () => action.mutate(name);
  const sheet = isSheet(doc);
  const open = doc.lines.filter((l) => !l.confirmed_at);
  const total = doc.lines.reduce((sum, l) => sum + l.qty_planned, 0);
  const done = doc.lines.filter((l) => l.confirmed_at).reduce((sum, l) => sum + l.qty_actual, 0);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={sheet ? "Putaway sheet" : docLabel} no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          (doc.status === "DRAFT" || doc.status === "TO_PUT_AWAY") && (
            <Space wrap>
              {doc.status === "TO_PUT_AWAY" && open.length > 0 ? (
                <Tooltip title={`${open.length} line${open.length === 1 ? "" : "s"} still to put away`}>
                  <Button type="primary" disabled>
                    Post
                  </Button>
                </Tooltip>
              ) : (
                <ActionButton
                  perm={`${PERM_PREFIX[path]}.post`}
                  type="primary"
                  label="Post"
                  confirm="Are the goods at the target location? Posting moves the stock immediately."
                  onConfirm={run("post")}
                  loading={action.isPending}
                />
              )}
              <ActionButton perm={`${PERM_PREFIX[path]}.cancel`} danger label="Cancel" confirm={`Cancel this ${docLabel.toLowerCase()}?`} onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={DESC_COLUMNS}>
          {path === "putaways" && (
            <Descriptions.Item label="Source goods receipt">
              {doc.ref_document ? <Link className="wms-mono" to={`/grns/${doc.ref_document.id}`}>{doc.ref_document.doc_no}</Link> : <span className="wms-empty-value">None</span>}
            </Descriptions.Item>
          )}
          {sheet && doc.location && <Descriptions.Item label="Take from">{doc.location.code} {doc.location.name}</Descriptions.Item>}
          {sheet && (
            <Descriptions.Item label="Put away">
              <div style={{ minWidth: 180 }}>
                <QtyProgress done={done} total={total} label="Put away" />
              </div>
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at) || <span className="wms-empty-value">Not yet</span>}</Descriptions.Item>
          <Descriptions.Item label="Remark">{doc.remark || <span className="wms-empty-value">—</span>}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="Lines">
        <DocumentLinesTable
          lines={doc.lines}
          columns={
            sheet
              ? [
                  { title: "Quantity", dataIndex: "qty_planned", align: "right", render: formatQty },
                  { title: "Batch no.", dataIndex: "batch_no" },
                  { title: "Expiry date", dataIndex: "expiry_date" },
                  {
                    title: "Bin",
                    render: (_, l) =>
                      l.confirmed_at ? (
                        <span className="wms-mono">{l.to_location?.code}</span>
                      ) : l.to_location ? (
                        <span>
                          <span className="wms-mono">{l.to_location.code}</span> <span className="wms-empty-value">suggested</span>
                        </span>
                      ) : (
                        <span className="wms-empty-value">Any bin</span>
                      ),
                  },
                  {
                    title: "Status",
                    render: (_, l) =>
                      l.confirmed_at ? (
                        <Pill tone="green" dot>Put away {formatDateTime(l.confirmed_at)}</Pill>
                      ) : doc.status === "TO_PUT_AWAY" && can("putaway.create") ? (
                        <Button size="small" onClick={() => setPutting(l)} data-testid={`put-${l.line_no}`}>
                          Put away…
                        </Button>
                      ) : (
                        <Pill tone="amber" dot>Open</Pill>
                      ),
                  },
                ]
              : [
                  { title: "Quantity", dataIndex: "qty_actual", align: "right", render: formatQty },
                  { title: "Batch no.", dataIndex: "batch_no" },
                  { title: "Expiry date", dataIndex: "expiry_date" },
                  { title: "From location", render: (_, l) => <span className="wms-mono">{l.from_location?.code}</span> },
                  { title: "To location", render: (_, l) => <span className="wms-mono">{l.to_location?.code}</span> },
                ]
          }
        />
      </Card>
      {putting && <PutModal sheet={doc} line={putting} onClose={() => setPutting(null)} />}
    </Space>
  );
}

/** Put away one sheet line from the web (when no PDA is at hand): which bin, how much */
function PutModal({ sheet, line, onClose }: { sheet: Document; line: DocumentLine; onClose: () => void }) {
  const [form] = Form.useForm<{ to_location_id: string; qty: number }>();
  const queryClient = useQueryClient();
  const put = useMutation({
    mutationFn: async (v: { to_location_id: string; qty: number }) =>
      (await apiClient.post<Document>(`/putaways/${sheet.id}/lines/${line.id}/put`, v)).data,
    onSuccess: (doc) => {
      message.success("Put away");
      queryClient.setQueryData(["putaways", sheet.id], doc);
      void queryClient.invalidateQueries({ queryKey: ["putaways"] });
      onClose();
    },
    onError: showError,
  });
  return (
    <Modal open title={`Put away ${line.item.sku_code} ${line.item.name}`} okText="Put away" onOk={() => form.submit()} confirmLoading={put.isPending} onCancel={onClose} destroyOnHidden>
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        initialValues={{ to_location_id: line.to_location?.id, qty: line.qty_planned }}
        onFinish={(v) => put.mutate(v)}
      >
        <Form.Item name="to_location_id" label="Bin" rules={[{ required: true }]}>
          <LocationSelect types={["BIN"]} placeholder="Scan or choose the bin" />
        </Form.Item>
        <Form.Item
          name="qty"
          label={`Quantity (${line.uom.code})`}
          rules={[{ required: true }]}
          extra={`Up to ${formatQty(line.qty_planned)}. Less splits the rest off as a new line, for another bin.`}
        >
          <InputNumber min={0.0001} max={line.qty_planned} style={{ width: 200 }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
