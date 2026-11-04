import { useState } from "react";

import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Form, Input, Select, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { BusinessPartner } from "@/api/types";
import MasterSearch, { MASTER_LIST_LIMIT } from "@/components/MasterSearch";
import { useColumnPrefs } from "@/components/ListTools";
import { YesNo } from "@/components/ui";
import CreateModal from "@/components/CreateModal";
import { PARTNER_TYPE_LABELS } from "@/constants/labels";

export default function BusinessPartnersPage() {
  const can = useCan();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["business-partners", keyword],
    queryFn: async () =>
      (await apiClient.get<BusinessPartner[]>("/business-partners", { params: { limit: MASTER_LIST_LIMIT, keyword: keyword || undefined } })).data,
  });

  const { columns, settings: columnSettings } = useColumnPrefs<BusinessPartner>("business-partners", [
    { title: "Code", dataIndex: "code" },
    { title: "Name", dataIndex: "name" },
    { title: "Type", dataIndex: "partner_type", render: (v: string) => PARTNER_TYPE_LABELS[v] ?? v },
    { title: "Contact", dataIndex: "contact_name" },
    { title: "Phone", dataIndex: "contact_phone" },
    { title: "Active", dataIndex: "is_active", render: (v: boolean) => <YesNo value={v} /> },
  ]);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <MasterSearch
        placeholder="Code / name" onSearch={setKeyword} shown={data?.length}
        actions={
          <>
            {columnSettings}
            {can("business_partner.create") && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
                New business partner
              </Button>
            )}
          </>
        }
      />
      <Table<BusinessPartner>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={columns}
      />
      <CreateModal
        open={creating}
        title="New business partner"
        path="/business-partners"
        queryKey="business-partners"
        initialValues={{ partner_type: "supplier" }}
        onClose={() => setCreating(false)}
      >
        {() => (
          <>
            <Form.Item name="code" label="Code" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="partner_type" label="Type" rules={[{ required: true }]}>
              <Select
                options={Object.entries(PARTNER_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
            <Form.Item name="contact_name" label="Contact">
              <Input />
            </Form.Item>
            <Form.Item name="contact_phone" label="Phone">
              <Input />
            </Form.Item>
            <Form.Item name="address" label="Address">
              <Input />
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
