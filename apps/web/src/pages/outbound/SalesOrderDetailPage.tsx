import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Checkbox, Descriptions, Form, Input, Modal, Space, Spin, Table, Typography, message } from "antd";
import { Link, useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan, useFeature } from "@/api/me";
import type { DocumentSummary, Pick, SalesOrder, SalesOrderLine, Shipment, Shortage } from "@/api/types";
import StatusTag from "@/components/StatusTag";
import { DocTitle } from "@/components/ui";
import { ActionButton, formatDateTime, useDocumentAction } from "@/components/documents";
import { LocationSelect } from "@/components/selects";

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

function RelatedDocs({ title, path, docs }: { title: string; path: string; docs?: DocumentSummary[] }) {
  return (
    <Card title={title}>
      <Table<DocumentSummary>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={docs}
        columns={[
          { title: "Document no.", dataIndex: "doc_no", render: (v: string, r) => <Link to={`/${path}/${r.id}`}>{v}</Link> },
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

  const { data: so, isLoading } = useQuery({
    queryKey: ["sales-orders", id],
    queryFn: async () => (await apiClient.get<SalesOrder>(`/sales-orders/${id}`)).data,
  });
  const { data: picks } = useQuery({
    queryKey: ["picks", "by-so", id],
    queryFn: async () => (await apiClient.get<DocumentSummary[]>("/picks", { params: { so_id: id } })).data,
  });
  const { data: shipments } = useQuery({
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
      refresh();
      message.success(`Created pick list ${pick.doc_no}`);
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

  if (isLoading || !so) return <Spin />;
  const run = (name: string) => () => action.mutate(name);
  const fulfilling = FULFILLING.includes(so.status);
  const hasUnallocated = so.lines.some((l) => l.unallocated > 0);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Sales order"} no={so.doc_no} status={so.status} historyOf={so.id} />}
        extra={
          <Space>
            {so.status === "DRAFT" && (
              <>
                {can("sales_order.update") && <Button onClick={() => navigate(`/sales-orders/${id}/edit`)}>Edit</Button>}
                <ActionButton perm="sales_order.confirm" type="primary" label="Confirm" confirm="The order cannot be edited after confirmation. Continue?" onConfirm={run("confirm")} loading={action.isPending} />
              </>
            )}
            {fulfilling && hasUnallocated && can("sales_order.allocate") && (
              <Button type="primary" onClick={() => setAllocating(true)}>
                Allocate stock
              </Button>
            )}
            {SHIPPABLE.includes(so.status) && can("shipment.create") && (
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
        <Descriptions column={3}>
          <Descriptions.Item label="Customer">
            {so.partner?.code} {so.partner?.name}
          </Descriptions.Item>
          <Descriptions.Item label="Requested ship date">{so.expected_date}</Descriptions.Item>
          <Descriptions.Item label="Created">{formatDateTime(so.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Remark" span={2}>
            {so.remark}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Lines and progress (progress in base units)">
        <Table<SalesOrderLine>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={so.lines}
          columns={[
            { title: "Line", dataIndex: "line_no", width: 60 },
            { title: "SKU", render: (_, l) => l.item.sku_code },
            { title: "Item", render: (_, l) => l.item.name },
            { title: "Ordered", render: (_, l) => `${l.qty_planned} ${l.uom.code}` },
            { title: "In base units", render: (_, l) => `${l.ordered_base} ${l.item.base_uom.code}` },
            { title: "Allocated (to pick)", dataIndex: "allocated" },
            { title: "Picked", dataIndex: "picked" },
            { title: "Shipped", dataIndex: "shipped" },
            {
              title: "Unallocated",
              dataIndex: "unallocated",
              render: (v: number) =>
                v > 0 && fulfilling ? <Typography.Text type="danger">{v}</Typography.Text> : v,
            },
            ...(feature("RETURNS") || so.lines.some((l) => l.returned > 0)
              ? [{ title: "Returned", dataIndex: "returned" }]
              : []),
          ]}
        />
      </Card>

      <RelatedDocs title="Pick lists" path="picks" docs={picks} />
      <RelatedDocs title="Shipments" path="shipments" docs={shipments} />

      <Modal
        open={allocating}
        title="Allocate stock"
        okText="Allocate"
        okButtonProps={{ disabled: !stagingId || (crossDock && !sourceId) }}
        confirmLoading={allocate.isPending}
        onOk={() => allocate.mutate()}
        onCancel={() => setAllocating(false)}
      >
        <p>Stock is reserved for the unallocated quantity by "first expiry first out, pickable bins first, first in first out", and a pick list is created.</p>
        <p>Put picked goods at:</p>
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
          <Space>
            <Form.Item name="vehicle_no" label="Vehicle plate">
              <Input maxLength={30} />
            </Form.Item>
            <Form.Item name="seal_no" label="Seal no.">
              <Input maxLength={50} />
            </Form.Item>
          </Space>
          <Space>
            <Form.Item name="driver_name" label="Driver">
              <Input maxLength={50} />
            </Form.Item>
            <Form.Item name="driver_phone" label="Driver phone">
              <Input maxLength={30} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Space>
  );
}
