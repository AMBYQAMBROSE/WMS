import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Button, Form, Input, Select, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { BusinessPartner } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import { PARTNER_TYPE_LABELS } from "@/constants/labels";

export default function BusinessPartnersPage() {
  const [creating, setCreating] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["business-partners"],
    queryFn: async () =>
      (await apiClient.get<BusinessPartner[]>("/business-partners", { params: { limit: 500 } })).data,
  });

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Button type="primary" onClick={() => setCreating(true)}>
        新建业务伙伴
      </Button>
      <Table<BusinessPartner>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "编码", dataIndex: "code" },
          { title: "名称", dataIndex: "name" },
          { title: "类型", dataIndex: "partner_type", render: (v: string) => PARTNER_TYPE_LABELS[v] ?? v },
          { title: "联系人", dataIndex: "contact_name" },
          { title: "电话", dataIndex: "contact_phone" },
          { title: "启用", dataIndex: "is_active", render: (v: boolean) => (v ? "是" : "否") },
        ]}
      />
      <CreateModal
        open={creating}
        title="新建业务伙伴"
        path="/business-partners"
        queryKey="business-partners"
        initialValues={{ partner_type: "supplier" }}
        onClose={() => setCreating(false)}
      >
        {() => (
          <>
            <Form.Item name="code" label="编码" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="partner_type" label="类型" rules={[{ required: true }]}>
              <Select
                options={Object.entries(PARTNER_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
            <Form.Item name="contact_name" label="联系人">
              <Input />
            </Form.Item>
            <Form.Item name="contact_phone" label="电话">
              <Input />
            </Form.Item>
            <Form.Item name="address" label="地址">
              <Input />
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
