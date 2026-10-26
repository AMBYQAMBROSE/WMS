import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Form, Input, InputNumber, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { Item } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import { UomSelect, useUoms } from "@/components/selects";

const yesNo = (v: boolean) => (v ? "是" : "否");

export default function ItemsPage() {
  const [creating, setCreating] = useState(false);
  const { data: uoms } = useUoms();
  const { data, isLoading } = useQuery({
    queryKey: ["items"],
    queryFn: async () => (await apiClient.get<Item[]>("/items", { params: { limit: 500 } })).data,
  });
  const uomCode = (id: string) => uoms?.find((u) => u.id === id)?.code ?? "";

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Button type="primary" onClick={() => setCreating(true)}>
        新建商品
      </Button>
      <Table<Item>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "SKU", dataIndex: "sku_code" },
          { title: "名称", dataIndex: "name" },
          { title: "条码", dataIndex: "barcode" },
          { title: "分类", dataIndex: "category" },
          { title: "基本单位", dataIndex: "base_uom_id", render: uomCode },
          { title: "批次管理", dataIndex: "is_batch_managed", render: yesNo },
          { title: "效期管理", dataIndex: "is_expiry_managed", render: yesNo },
          { title: "启用", dataIndex: "is_active", render: yesNo },
        ]}
      />
      <CreateModal
        open={creating}
        title="新建商品"
        path="/items"
        queryKey="items"
        initialValues={{ is_batch_managed: false, is_expiry_managed: false }}
        onClose={() => setCreating(false)}
      >
        {() => (
          <>
            <Form.Item name="sku_code" label="SKU" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="base_uom_id" label="基本单位" rules={[{ required: true }]}>
              <UomSelect />
            </Form.Item>
            <Form.Item name="barcode" label="条码">
              <Input />
            </Form.Item>
            <Form.Item name="category" label="分类">
              <Input />
            </Form.Item>
            <Form.Item name="is_batch_managed" valuePropName="checked">
              <Checkbox>批次管理</Checkbox>
            </Form.Item>
            <Form.Item name="is_expiry_managed" valuePropName="checked">
              <Checkbox>效期管理</Checkbox>
            </Form.Item>
            <Form.Item name="shelf_life_days" label="保质期（天）">
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
