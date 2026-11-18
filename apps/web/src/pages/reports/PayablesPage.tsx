import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Segmented, Space, Table, Typography } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { PayablePage, PayableRow } from "@/api/types";
import { formatDateTime } from "@/components/documents";
import { PayableStatus, SettleControls } from "@/components/payables";
import { PartnerSelect } from "@/components/selects";
import { STICKY_HEADER, Toolbar, emptyLocale, formatMoney } from "@/components/ui";

type Status = "open" | "overdue" | "settled" | "all";

/** Supplier payables: posted goods receipts, their due dates from the supplier's credit terms, and settlement */
export default function PayablesPage() {
  const [status, setStatus] = useState<Status>("open");
  const [partnerId, setPartnerId] = useState<string>();
  const { data, isLoading } = useQuery({
    queryKey: ["payables", status, partnerId],
    queryFn: async () =>
      (await apiClient.get<PayablePage>("/payables", { params: { status: status === "all" ? undefined : status, partner_id: partnerId } })).data,
    placeholderData: (previous) => previous,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size="middle">
      <Row gutter={16}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Typography.Text type="secondary">Outstanding</Typography.Text>
            <div className="wms-num" style={{ fontSize: 22, fontWeight: 600 }}>{formatMoney(data?.outstanding)}</div>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Typography.Text type="secondary">Overdue</Typography.Text>
            <div className="wms-num" style={{ fontSize: 22, fontWeight: 600, color: data?.overdue ? "var(--wms-tone-red-fg)" : undefined }}>
              {formatMoney(data?.overdue)}
            </div>
          </Card>
        </Col>
      </Row>
      <Toolbar
        left={
          <>
            <Segmented
              value={status}
              onChange={(v) => setStatus(v as Status)}
              options={[
                { value: "open", label: "Open" },
                { value: "overdue", label: "Overdue" },
                { value: "settled", label: "Settled" },
                { value: "all", label: "All" },
              ]}
            />
            <PartnerSelect allowClear placeholder="Filter by supplier" style={{ width: 260 }} value={partnerId} onChange={setPartnerId} aria-label="Filter by supplier" />
          </>
        }
        right={data && <span className="wms-toolbar-meta">{data.total.toLocaleString()} receipts</span>}
      />
      <Table<PayableRow>
        rowKey="id"
        loading={isLoading}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        dataSource={data?.rows}
        pagination={{ pageSize: 50, showSizeChanger: true }}
        locale={emptyLocale(status === "open" ? "Nothing outstanding" : "No receipts")}
        rowClassName={(r) => (r.status === "overdue" ? "wms-alarm-row" : "")}
        columns={[
          { title: "Receipt", dataIndex: "doc_no", render: (v: string, r) => <Link className="wms-mono" to={`/grns/${r.id}`}>{v}</Link> },
          { title: "Supplier", render: (_, r) => r.partner.name },
          { title: "Terms", render: (_, r) => (r.credit_terms_days ? `${r.credit_terms_days} days` : "On receipt") },
          { title: "Received", dataIndex: "posted_at", render: formatDateTime },
          { title: "Due", dataIndex: "payment_due_date" },
          { title: "Amount", align: "right", render: (_, r) => <span className="wms-num">{formatMoney(r.value)}</span> },
          { title: "Status", render: (_, r) => <PayableStatus due={r.payment_due_date} settledOn={r.settled_on} /> },
          { title: "", key: "action", render: (_, r) => <SettleControls grnId={r.id} settledOn={r.settled_on} postedAt={r.posted_at} /> },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        Each posted goods receipt is due its supplier's credit terms after posting (set on the supplier under Business partners). The WMS does not
        record invoices or payments: mark a receipt settled once accounts have paid it. Amounts are at purchase order prices, excluding tax.
      </Typography.Text>
    </Space>
  );
}
