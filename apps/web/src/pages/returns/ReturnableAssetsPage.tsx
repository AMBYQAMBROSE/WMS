import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, InputNumber, Modal, Radio, Space, Table, Tabs, Tag, message } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { AssetBalance, AssetTxn, AssetType } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import { formatDateTime, preventEnterSubmit } from "@/components/documents";
import { PartnerSelect } from "@/components/selects";

const KEY = "returnable-assets";

interface TxnValues {
  partner_id: string;
  asset_type_id: string;
  txn_type: "ISSUE" | "RETURN";
  qty: number;
  remark?: string;
}

/** Returnable assets (pallets, crates, ...): lend to and take back from partners, outstanding quantity per partner x type */
export default function ReturnableAssetsPage() {
  const can = useCan();
  const queryClient = useQueryClient();
  const [recording, setRecording] = useState<TxnValues["txn_type"] | null>(null);
  const [creatingType, setCreatingType] = useState(false);
  const [partnerId, setPartnerId] = useState<string>();
  const [form] = Form.useForm<TxnValues>();

  const types = useQuery({
    queryKey: [KEY, "types"],
    queryFn: async () => (await apiClient.get<AssetType[]>("/returnable-assets/types")).data,
  });
  const balances = useQuery({
    queryKey: [KEY, "balances", partnerId],
    queryFn: async () =>
      (
        await apiClient.get<AssetBalance[]>("/returnable-assets/balances", {
          params: { partner_id: partnerId },
        })
      ).data,
  });
  const txns = useQuery({
    queryKey: [KEY, "transactions"],
    queryFn: async () => (await apiClient.get<AssetTxn[]>("/returnable-assets/transactions")).data,
  });

  const record = useMutation({
    mutationFn: (values: TxnValues) => apiClient.post("/returnable-assets/transactions", values),
    onSuccess: () => {
      message.success("Recorded");
      queryClient.invalidateQueries({ queryKey: [KEY] });
      setRecording(null);
    },
    onError: showError,
  });

  const open = (txn_type: TxnValues["txn_type"], preset?: Partial<TxnValues>) => {
    form.resetFields();
    form.setFieldsValue({ txn_type, ...preset });
    setRecording(txn_type);
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      {can("returnable_asset.manage") && (
        <Space>
          <Button type="primary" onClick={() => open("ISSUE")}>
            Record issue
          </Button>
          <Button onClick={() => open("RETURN")}>Record return</Button>
        </Space>
      )}
      <Tabs
        items={[
          {
            key: "balances",
            label: "Outstanding",
            children: (
              <Space orientation="vertical" style={{ width: "100%" }}>
                <PartnerSelect
                  allowClear
                  placeholder="Filter by partner"
                  style={{ width: 280 }}
                  value={partnerId}
                  onChange={setPartnerId}
                  data-testid="balance-partner"
                />
                <Table<AssetBalance>
                  rowKey={(r) => `${r.partner.id}-${r.asset_type.id}`}
                  loading={balances.isLoading}
                  dataSource={balances.data}
                  columns={[
                    {
                      title: "Partner",
                      render: (_, r) => `${r.partner.code} ${r.partner.name}`,
                    },
                    {
                      title: "Asset type",
                      render: (_, r) => `${r.asset_type.code} ${r.asset_type.name}`,
                    },
                    { title: "Outstanding", dataIndex: "outstanding" },
                    {
                      title: "Actions",
                      render: (_, r) =>
                        can("returnable_asset.manage") && (
                          <Button
                            size="small"
                            onClick={() =>
                              open("RETURN", {
                                partner_id: r.partner.id,
                                asset_type_id: r.asset_type.id,
                                qty: r.outstanding,
                              })
                            }
                          >
                            Return
                          </Button>
                        ),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "transactions",
            label: "Transactions",
            children: (
              <Table<AssetTxn>
                rowKey="id"
                loading={txns.isLoading}
                dataSource={txns.data}
                columns={[
                  {
                    title: "Time",
                    dataIndex: "occurred_at",
                    render: formatDateTime,
                  },
                  {
                    title: "Partner",
                    render: (_, r) => `${r.partner.code} ${r.partner.name}`,
                  },
                  { title: "Asset type", render: (_, r) => r.asset_type.name },
                  {
                    title: "Type",
                    dataIndex: "txn_type",
                    render: (t: string) =>
                      t === "ISSUE" ? <Tag color="orange">Issued</Tag> : <Tag color="green">Returned</Tag>,
                  },
                  { title: "Quantity", dataIndex: "qty_change" },
                  { title: "Remark", dataIndex: "remark" },
                ]}
              />
            ),
          },
          {
            key: "types",
            label: "Asset types",
            children: (
              <Space orientation="vertical" style={{ width: "100%" }}>
                {can("returnable_asset.manage") && <Button onClick={() => setCreatingType(true)}>New asset type</Button>}
                <Table<AssetType>
                  rowKey="id"
                  loading={types.isLoading}
                  dataSource={types.data}
                  pagination={false}
                  columns={[
                    { title: "Code", dataIndex: "code" },
                    { title: "Name", dataIndex: "name" },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      render: (v: boolean) => (v ? "Yes" : "No"),
                    },
                  ]}
                />
              </Space>
            ),
          },
        ]}
      />
      <Modal
        open={!!recording}
        title={recording === "ISSUE" ? "Record issue" : "Record return"}
        onCancel={() => setRecording(null)}
        onOk={() => form.submit()}
        confirmLoading={record.isPending}
        forceRender
      >
        <Form form={form} layout="vertical" onKeyDown={preventEnterSubmit} onFinish={(v) => record.mutate(v)}>
          <Form.Item name="txn_type" label="Type">
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio value="ISSUE">Issue</Radio>
              <Radio value="RETURN">Return</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="partner_id" label="Partner" rules={[{ required: true }]}>
            <PartnerSelect />
          </Form.Item>
          <Form.Item name="asset_type_id" label="Asset type" rules={[{ required: true }]}>
            <Radio.Group
              options={(types.data ?? []).filter((t) => t.is_active).map((t) => ({ value: t.id, label: t.name }))}
            />
          </Form.Item>
          <Form.Item name="qty" label="Quantity" rules={[{ required: true }]}>
            <InputNumber min={1} precision={0} />
          </Form.Item>
          <Form.Item name="remark" label="Remark">
            <Input maxLength={400} />
          </Form.Item>
        </Form>
      </Modal>
      <CreateModal<AssetType>
        open={creatingType}
        title="New asset type"
        path="/returnable-assets/types"
        queryKey={KEY}
        onClose={() => setCreatingType(false)}
      >
        {() => (
          <>
            <Form.Item name="code" label="Code" rules={[{ required: true }]}>
              <Input maxLength={30} />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input maxLength={100} />
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
