import { useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Checkbox, Col, Descriptions, Form, Input, Modal, Row, Space, Table, Typography, message } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan, useFeature } from "@/api/me";
import type { DocumentSummary, Pick, SalesOrder, SalesOrderLine, Shipment, Shortage } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, QtyProgress, emptyLocale, formatQty } from "@/components/ui";
import { SalesOrderSteps } from "@/components/workflows";
import { ActionButton, formatDateTime, offerPrint, useDocumentAction } from "@/components/documents";
import { LocationSelect } from "@/components/selects";
import { useLastLocation } from "@/components/stockAutofill";

const FULFILLING = ["CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED"];
const SHIPPABLE = ["IN_PROGRESS", "PARTIALLY_SHIPPED"];
// Returns are only possible once something has shipped
const RETURNABLE = ["PARTIALLY_SHIPPED", "SHIPPED", "CLOSED"];

interface ShipForm {
  carrier?: string;
  vehicle_no?: string;
  driver_name?: string;
  driver_phone?: string;
  seal_no?: string;
}

function RelatedDocs({ title, path, docs, loading }: { title: string; path: string; docs?: DocumentSummary[]; loading?: boolean }) {
  return (
    <Card title={title}>
      <Table<DocumentSummary>
        rowKey="id"
        size="small"
        pagination={false}
        loading={loading}
        dataSource={docs}
        scroll={{ x: "max-content" }}
        locale={emptyLocale(`No ${title.toLowerCase()} yet`)}
        columns={[
          { title: "Document no.", dataIndex: "doc_no", render: (v: string, r) => <Link className="wms-mono" to={`/${path}/${r.id}`}>{v}</Link> },
          { title: "Status", dataIndex: "status", render: (v: string) => <StatusTag status={v} /> },
          { title: "Created", dataIndex: "created_at", render: formatDateTime },
          { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        ]}
      />
    </Card>
  );
}

export default function SalesOrderDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
  const feature = useFeature();
  const queryClient = useQueryClient();
  const [allocating, setAllocating] = useState(false);
  const [shipping, setShipping] = useState(false);
  const [stagingId, setStagingId] = useState<string>();
  // Cross-docking: allocate straight from the receiving dock (DOCK), without putaway
  const [crossDock, setCrossDock] = useState(false);
  const [sourceId, setSourceId] = useState<string>();
  const [shipForm] = Form.useForm<ShipForm>();
  // Picked goods nearly always go to the same staging area: start with the one used last time
  const [lastStaging, rememberStaging] = useLastLocation("staging");
  useEffect(() => {
    if (lastStaging) setStagingId((current) => current ?? lastStaging);
  }, [lastStaging]);

  const { data: so, isLoading, error, refetch } = useQuery({
    queryKey: ["sales-orders", id],
    queryFn: async () => (await apiClient.get<SalesOrder>(`/sales-orders/${id}`)).data,
  });
  const { data: picks, isLoading: picksLoading } = useQuery({
    queryKey: ["picks", "by-so", id],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/picks", { params: { so_id: id } })).data,
  });
  const { data: shipments, isLoading: shipmentsLoading } = useQuery({
    queryKey: ["shipments", "by-so", id],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/shipments", { params: { so_id: id } })).data,
  });
  const action = useDocumentAction("sales-orders", id);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
    queryClient.invalidateQueries({ queryKey: ["picks"] });
    queryClient.invalidateQueries({ queryKey: ["shipments"] });
    queryClient.invalidateQueries({ queryKey: ["stock"] });
  };

  const allocate = useMutation({
    mutationFn: async () =>
      (
        await apiClient.post<{ pick: Pick; shortages: Shortage[] }>(`/sales-orders/${id}/allocate`, {
          staging_location_id: stagingId,
          source_location_id: crossDock ? sourceId : null,
        })
      ).data,
    onSuccess: ({ pick, shortages }) => {
      setAllocating(false);
      rememberStaging(stagingId);
      refresh();
      message.success({
        key: `pick-${pick.id}`,
        duration: 8,
        content: (
          <span>
            {/* Not a <Link>: messages render outside the router */}
            Created pick list <a onClick={() => navigate(`/picks/${pick.id}`)} data-testid="open-pick">{pick.doc_no}</a>
          </span>
        ),
      });
      // The picker works from the paper list: bring it up, ready to print
      offerPrint(pick);
      if (shortages.length) {
        Modal.warning({
          title: "Some items are short; not everything could be allocated",
          content: (
            <ul>
              {shortages.map((s) => (
                <li key={s.line_id}>
                  {s.sku_code} {s.name}: short {s.qty} {s.uom_code}
                </li>
              ))}
            </ul>
          ),
        });
      }
    },
    onError: showError,
  });

  const ship = useMutation({
    mutationFn: async (values: ShipForm) =>
      (await apiClient.post<Shipment>("/shipments", { so_id: id, ...values })).data,
    onSuccess: (doc) => {
      setShipping(false);
      refresh();
      message.success(`Created shipment ${doc.doc_no}; post it once loading is done`);
      navigate(`/shipments/${doc.id}`);
    },
    onError: showError,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!so) return <ErrorState title="Could not load this sales order" error={error} onRetry={() => refetch()} back={{ to: "/sales-orders", label: "Back to sales orders" }} />;
  const run = (name: string) => () => action.mutate(name);
  // Confirming is followed by allocating: go straight on to it instead of leaving the user to find the next button
  const confirmOrder = () =>
    action.mutate("confirm", { onSuccess: () => can("sales_order.allocate") && setAllocating(true) });
  const fulfilling = FULFILLING.includes(so.status);
  const hasUnallocated = so.lines.some((l) => l.unallocated > 0);
  // Something is picked and waiting in staging: only then is there anything to ship
  const hasStaged = so.lines.some((l) => l.picked > l.shipped);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Sales order"} no={so.doc_no} status={so.status} historyOf={so.id} />}
        extra={
          <Space wrap>
            {so.status === "DRAFT" && (
              <>
                {can("sales_order.update") && <Button onClick={() => navigate(`/sales-orders/${id}/edit`)}>Edit</Button>}
                <ActionButton perm="sales_order.confirm" type="primary" label="Confirm" confirm="The order cannot be edited after confirmation. Continue?" onConfirm={confirmOrder} loading={action.isPending} />
              </>
            )}
            {fulfilling && hasUnallocated && can("sales_order.allocate") && (
              <Button type="primary" onClick={() => setAllocating(true)}>
                Allocate stock
              </Button>
            )}
            {SHIPPABLE.includes(so.status) && hasStaged && can("shipment.create") && (
              <Button onClick={() => setShipping(true)}>Ship</Button>
            )}
            {feature("RETURNS") && RETURNABLE.includes(so.status) && can("return_in.create") && (
              <Button onClick={() => navigate(`/returns-in/new?so=${id}`)}>Customer return</Button>
            )}
            {fulfilling && so.status !== "CONFIRMED" && (
              <ActionButton perm="sales_order.close" label="Close" confirm="The remaining unshipped quantity will not be shipped. Continue?" onConfirm={run("close")} loading={action.isPending} />
            )}
            {(so.status === "DRAFT" || fulfilling) && (
              <ActionButton perm="sales_order.cancel" danger label="Cancel" confirm="Cancel this order?" onConfirm={run("cancel")} loading={action.isPending} />
            )}
          </Space>
        }
      >
        <SalesOrderSteps status={so.status} shippedAny={so.lines.some((l) => l.shipped > 0)} />
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Customer">
            {so.partner?.code} {so.partner?.name}
          </Descriptions.Item>
          <Descriptions.Item label="Requested ship date">{so.expected_date ?? <span className="wms-empty-value">Not set</span>}</Descriptions.Item>
          <Descriptions.Item label="Created">{formatDateTime(so.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark" span="filled">
            {so.remark || <span className="wms-empty-value">—</span>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines and progress" extra={<Typography.Text type="secondary">Progress in base units</Typography.Text>}>
        <Table<SalesOrderLine>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={so.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "#", dataIndex: "line_no", width: 48, render: (v: number) => <Typography.Text type="secondary" className="wms-num">{v}</Typography.Text> },
            { title: "SKU", render: (_, l) => <span className="wms-mono">{l.item.sku_code}</span> },
            { title: "Item", render: (_, l) => l.item.name },
            { title: "Ordered", align: "right", render: (_, l) => `${formatQty(l.qty_planned)} ${l.uom.code}` },
            { title: "In base units", align: "right", render: (_, l) => `${formatQty(l.ordered_base)} ${l.item.base_uom.code}` },
            { title: "Allocated (to pick)", dataIndex: "allocated", align: "right", render: formatQty },
            { title: "Picked", dataIndex: "picked", align: "right", render: formatQty },
            { title: "Shipped", key: "shipped", render: (_, l) => <QtyProgress done={l.shipped} total={l.ordered_base} label="Shipped" /> },
            {
              title: "Unallocated",
              dataIndex: "unallocated",
              align: "right",
              render: (v: number) =>
                v > 0 && fulfilling ? <Typography.Text type="danger" strong>{formatQty(v)}</Typography.Text> : formatQty(v),
            },
            ...(feature("RETURNS") || so.lines.some((l) => l.returned > 0)
              ? [{ title: "Returned", dataIndex: "returned", align: "right" as const, render: formatQty }]
              : []),
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <RelatedDocs title="Pick lists" path="picks" docs={picks} loading={picksLoading} />
        </Col>
        <Col xs={24} xl={12}>
          <RelatedDocs title="Shipments" path="shipments" docs={shipments} loading={shipmentsLoading} />
        </Col>
      </Row>

      <Modal
        open={allocating}
        title="Allocate stock"
        okText="Allocate"
        okButtonProps={{ disabled: !stagingId || (crossDock && !sourceId) }}
        confirmLoading={allocate.isPending}
        onOk={() => allocate.mutate()}
        onCancel={() => setAllocating(false)}
      >
        <Typography.Paragraph type="secondary">
          Stock is reserved for the unallocated quantity by “first expiry first out, pickable bins first, first in first out”, and a pick list is created.
        </Typography.Paragraph>
        <Typography.Text strong style={{ display: "block", marginBottom: 6 }}>
          Put picked goods at
        </Typography.Text>
        <LocationSelect
          types={["DOCK"]}
          style={{ width: "100%" }}
          placeholder="Choose a shipping staging location"
          value={stagingId}
          onChange={setStagingId}
          data-testid="staging-select"
        />
        {feature("CROSS_DOCK") && (
          <div style={{ marginTop: 16 }}>
            <Checkbox checked={crossDock} onChange={(e) => setCrossDock(e.target.checked)}>
              Cross-dock: pick straight from the receiving dock (goods not put away)
            </Checkbox>
            {crossDock && (
              <LocationSelect
                types={["DOCK"]}
                style={{ width: "100%", marginTop: 8 }}
                placeholder="Choose the receiving dock holding the goods"
                value={sourceId}
                onChange={setSourceId}
                data-testid="source-select"
              />
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={shipping}
        title="Ship (everything picked but not yet shipped in staging)"
        okText="Create shipment"
        confirmLoading={ship.isPending}
        onOk={() => shipForm.submit()}
        onCancel={() => setShipping(false)}
        destroyOnHidden
      >
        {/* preserve=false: the form unmounts and clears when the modal closes, so it opens blank next time */}
        <Form form={shipForm} layout="vertical" preserve={false} onFinish={(v) => ship.mutate(v)}>
          <Form.Item name="carrier" label="Carrier">
            <Input maxLength={100} />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} sm={12}>
              <Form.Item name="vehicle_no" label="Vehicle plate">
                <Input maxLength={30} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="seal_no" label="Seal no.">
                <Input maxLength={50} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="driver_name" label="Driver">
                <Input maxLength={50} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="driver_phone" label="Driver phone">
                <Input maxLength={30} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Space>
  );
}
