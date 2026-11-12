import { useState } from "react";

import { PrinterOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, Form, InputNumber, Space, Table } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { DocumentSummary } from "@/api/types";
import { PrintLabelsModal } from "@/components/labels";
import StatusTag from "@/components/StatusTag";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, emptyLocale, formatQty } from "@/components/ui";
import {
  ActionButton,
  DocumentLinesTable,
  formatDateTime,
  useDocument,
  useDocumentAction,
} from "@/components/documents";

export default function GrnDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
  const { data: grn, isLoading, error, refetch } = useDocument("grns", id);
  const queryClient = useQueryClient();
  const [printingLabels, setPrintingLabels] = useState(false);
  const action = useDocumentAction("grns", id, {
    // Posting into a dock makes a putaway sheet: offer it for printing with the receipt
    madeByPosting: async (doc) => {
      void queryClient.invalidateQueries({ queryKey: ["putaways"] });
      return (await apiClient.get<DocumentSummary[]>("/putaways", { params: { ref_document_id: doc.id, status: "TO_PUT_AWAY" } })).data;
    },
  });
  const { data: putaways, isLoading: putawaysLoading } = useQuery({
    queryKey: ["putaways", "by-grn", id],
    queryFn: async () =>
      (await apiClient.get<DocumentSummary[]>("/putaways", { params: { grn_id: id } })).data,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!grn) return <ErrorState title="Could not load this goods receipt" error={error} onRetry={() => refetch()} back={{ to: "/grns", label: "Back to goods receipts" }} />;
  const run = (name: string) => () => action.mutate(name);
  const openSheet = putaways?.find((p) => p.status === "TO_PUT_AWAY");
  const tracked = grn.lines.some((l) => l.batch_no || l.expiry_date);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Goods receipt"} no={grn.doc_no} status={grn.status} historyOf={grn.id} />}
        extra={
          <Space wrap>
            {grn.status === "DRAFT" && (
              <>
                <ActionButton perm="grn.post" type="primary" label="Post" confirm="Posting increases stock immediately and cannot be undone. Continue?" onConfirm={run("post")} loading={action.isPending} />
                <ActionButton perm="grn.cancel" danger label="Cancel" confirm="Cancel this goods receipt?" onConfirm={run("cancel")} loading={action.isPending} />
              </>
            )}
            {grn.status === "POSTED" && (
              <Button key="stock-labels" icon={<PrinterOutlined />} onClick={() => setPrintingLabels(true)} data-testid="print-stock-labels">
                Print stock labels
              </Button>
            )}
            {grn.status === "POSTED" && can("putaway.create") && (
              <Button
                key="create"
                type={openSheet ? "default" : "primary"}
                title={openSheet ? `Plan the putaway here instead; replaces sheet ${openSheet.doc_no} if nothing on it is put away yet` : undefined}
                onClick={() => navigate(`/putaways/new?grn=${id}`)}
              >
                Create putaway
              </Button>
            )}
            {openSheet && (
              <Button key="sheet" type="primary" onClick={() => navigate(`/putaways/${openSheet.id}`)}>
                Putaway sheet {openSheet.doc_no}
              </Button>
            )}
          </Space>
        }
      >
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Purchase order">
            {grn.ref_document ? <Link className="wms-mono" to={`/purchase-orders/${grn.ref_document.id}`}>{grn.ref_document.doc_no}</Link> : <span className="wms-empty-value">None</span>}
          </Descriptions.Item>
          <Descriptions.Item label="Supplier">{grn.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Receiving location">{grn.location?.code} {grn.location?.name}</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(grn.posted_at) || <span className="wms-empty-value">Not yet</span>}</Descriptions.Item>
          <Descriptions.Item label="Remark">{grn.remark}</Descriptions.Item>
        </Descriptions>
      </Card>

      <PrintLabelsModal
        open={printingLabels}
        purpose="STOCK"
        path="/labels/stock"
        body={{ grn_id: grn.id }}
        maxCopies={20}
        summary={
          tracked
            ? "One label per carton or pallet: its QR code holds the item, batch, expiry and quantity, so putting away, picking, counting and loading need nothing typed."
            : "One label per carton or pallet: its QR code holds the item and quantity, so later scans need nothing typed."
        }
        onClose={() => setPrintingLabels(false)}
      >
        <Form.Item
          name="qty_per_label"
          label="Quantity per carton or pallet"
          extra="Leave empty for one label per line with the whole quantity. With 24, a line of 50 gets labels of 24, 24 and 2."
        >
          <InputNumber min={0.0001} style={{ width: 200 }} data-testid="qty-per-label" />
        </Form.Item>
      </PrintLabelsModal>

      <Card title="Lines">
        <DocumentLinesTable
          lines={grn.lines}
          columns={[
            { title: "Open at creation", dataIndex: "qty_planned", align: "right", render: formatQty },
            { title: "Received", dataIndex: "qty_actual", align: "right", render: formatQty },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
          ]}
        />
      </Card>

      <Card title="Putaways">
        <Table<DocumentSummary>
          rowKey="id"
          size="small"
          pagination={false}
          loading={putawaysLoading}
          dataSource={putaways}
          locale={emptyLocale("No putaways yet")}
          columns={[
            { title: "Putaway no.", dataIndex: "doc_no", render: (v: string, r) => <Link className="wms-mono" to={`/putaways/${r.id}`}>{v}</Link> },
            { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
            { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
          ]}
        />
      </Card>
    </Space>
  );
}
