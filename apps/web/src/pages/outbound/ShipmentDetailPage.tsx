import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, Form, Input, Space, Spin, message } from "antd";
import { Link, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Shipment, ShipmentInfo } from "@/api/types";
import { DocTitle } from "@/components/ui";
import { ActionButton, DocumentLinesTable, formatDateTime, preventEnterSubmit, useDocumentAction } from "@/components/documents";

const INFO_FIELDS: [keyof ShipmentInfo, string, number][] = [
  ["carrier", "Carrier", 100],
  ["vehicle_no", "Vehicle plate", 30],
  ["driver_name", "Driver", 50],
  ["driver_phone", "Driver phone", 30],
  ["seal_no", "Seal no.", 50],
];

export default function ShipmentDetailPage() {
  const { id = "" } = useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<ShipmentInfo>();
  const queryKey = ["shipments", id];
  const { data: ship, isLoading } = useQuery({
    queryKey,
    queryFn: async () => (await apiClient.get<Shipment>(`/shipments/${id}`)).data,
  });
  const action = useDocumentAction("shipments", id);

  const saveInfo = useMutation({
    mutationFn: async (values: ShipmentInfo) => (await apiClient.put<Shipment>(`/shipments/${id}/info`, values)).data,
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKey, updated);
      message.success("Loading details saved");
    },
    onError: showError,
  });

  if (isLoading || !ship) return <Spin />;
  const draft = ship.status === "DRAFT";
  const editable = draft && can("shipment.create");
  const run = (name: string) => () => action.mutate(name);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Shipment"} no={ship.doc_no} status={ship.status} />}
        extra={
          draft && (
            <Space>
              <ActionButton
                perm="shipment.post"
                type="primary"
                label="Post shipment"
                confirm="Has the truck been loaded and left? Posting ships the stock out of staging and updates the order to shipped/partially shipped."
                onConfirm={run("post")}
                loading={action.isPending}
              />
              <ActionButton perm="shipment.cancel" danger label="Cancel" confirm="Cancel this shipment?" onConfirm={run("cancel")} loading={action.isPending} />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="Sales order">
            {ship.ref_document && <Link to={`/sales-orders/${ship.ref_document.id}`}>{ship.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="Customer">{ship.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(ship.posted_at)}</Descriptions.Item>
          {!editable &&
            INFO_FIELDS.map(([key, label]) => (
              <Descriptions.Item key={key} label={label}>
                {ship.shipment_info?.[key]}
              </Descriptions.Item>
            ))}
        </Descriptions>
      </Card>

      {editable && (
        <Card title="Loading details">
          {/* initialValues instead of setFieldsValue: after posting the form no longer renders, and calling methods on an unmounted form warns */}
          <Form
            form={form}
            layout="inline"
            initialValues={ship.shipment_info ?? {}}
            onKeyDown={preventEnterSubmit}
            onFinish={(v) => saveInfo.mutate(v)}
          >
            {INFO_FIELDS.map(([key, label, max]) => (
              <Form.Item key={key} name={key} label={label}>
                <Input maxLength={max} style={{ width: 150 }} />
              </Form.Item>
            ))}
            <Button htmlType="submit" loading={saveInfo.isPending}>
              Save loading details
            </Button>
          </Form>
        </Card>
      )}

      <Card title="Shipment lines (base units)">
        <DocumentLinesTable
          lines={ship.lines}
          columns={[
            { title: "Quantity", dataIndex: "qty_actual" },
            { title: "Batch no.", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            { title: "Staging", render: (_, l) => l.from_location?.code },
          ]}
        />
      </Card>
    </Space>
  );
}
