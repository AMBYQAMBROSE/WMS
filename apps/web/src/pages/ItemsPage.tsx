import { useState } from "react";

import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Col, Form, Input, InputNumber, Row, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { Item } from "@/api/types";
import MasterSearch, { MASTER_LIST_LIMIT } from "@/components/MasterSearch";
import { useColumnPrefs } from "@/components/ListTools";
import { FormSection, STICKY_HEADER, YesNo } from "@/components/ui";
import CreateModal from "@/components/CreateModal";
import { UomSelect, useUoms } from "@/components/selects";

const yesNo = (v: boolean) => <YesNo value={v} />;

export default function ItemsPage() {
  const can = useCan();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const { data: uoms } = useUoms();
  const { data, isLoading } = useQuery({
    queryKey: ["items", keyword],
    queryFn: async () => (await apiClient.get<Item[]>("/items", { params: { limit: MASTER_LIST_LIMIT, keyword: keyword || undefined } })).data,
  });
  const uomCode = (id: string) => uoms?.find((u) => u.id === id)?.code ?? "";

  const { columns, settings: columnSettings } = useColumnPrefs<Item>("items", [
    { title: "SKU", dataIndex: "sku_code", render: (v: string) => <span className="wms-mono">{v}</span> },
    { title: "Name", dataIndex: "name" },
    { title: "Barcode", dataIndex: "barcode", render: (v: string | null) => (v ? <span className="wms-code">{v}</span> : <span className="wms-empty-value">—</span>) },
    { title: "Category", dataIndex: "category" },
    { title: "Base unit", dataIndex: "base_uom_id", render: uomCode },
    { title: "Batch managed", dataIndex: "is_batch_managed", render: yesNo },
    { title: "Expiry managed", dataIndex: "is_expiry_managed", render: yesNo },
    { title: "Active", dataIndex: "is_active", render: yesNo },
  ]);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <MasterSearch
        placeholder="SKU / name / barcode" onSearch={setKeyword} shown={data?.length}
        actions={
          <>
            {columnSettings}
            {can("item.create") && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
                New item
              </Button>
            )}
          </>
        }
      />
      <Table<Item>
        rowKey="id"
        loading={isLoading}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (t) => `${t.toLocaleString()} records` }}
        dataSource={data}
        columns={columns}
      />
      <CreateModal
        open={creating}
        title="New item"
        path="/items"
        queryKey="items"
        initialValues={{ is_batch_managed: false, is_expiry_managed: false }}
        onClose={() => setCreating(false)}
      >
        {() => (
          <>
            <Row gutter={12}>
              <Col xs={24} sm={10}>
                <Form.Item name="sku_code" label="SKU" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} sm={14}>
                <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} sm={10}>
                <Form.Item name="base_uom_id" label="Base unit" rules={[{ required: true }]}>
                  <UomSelect />
                </Form.Item>
              </Col>
              <Col xs={24} sm={14}>
                <Form.Item name="barcode" label="Barcode">
                  <Input placeholder="Optional; scan or type" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="category" label="Category">
                  <Input placeholder="Optional" />
                </Form.Item>
              </Col>
            </Row>
            <FormSection title="Tracking" description="Batch and expiry tracking cannot be added later without stock adjustments.">
              <Form.Item name="is_batch_managed" valuePropName="checked" style={{ marginBottom: 8 }}>
                <Checkbox>Batch managed</Checkbox>
              </Form.Item>
              <Form.Item name="is_expiry_managed" valuePropName="checked">
                <Checkbox>Expiry managed</Checkbox>
              </Form.Item>
              <Form.Item name="shelf_life_days" label="Shelf life (days)">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </FormSection>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
