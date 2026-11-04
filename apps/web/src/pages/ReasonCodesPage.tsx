import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Button, Form, Input, Segmented, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { ReasonCode } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import { YesNo } from "@/components/ui";

const CATEGORIES = { ADJUST: "Adjustment reasons", RETURN: "Return reasons" };

export default function ReasonCodesPage() {
  const can = useCan();
  const [creating, setCreating] = useState(false);
  const [category, setCategory] = useState<keyof typeof CATEGORIES>("ADJUST");
  const label = CATEGORIES[category];
  const { data, isLoading } = useQuery({
    queryKey: ["reason-codes", category],
    queryFn: async () => (await apiClient.get<ReasonCode[]>("/reason-codes", { params: { category } })).data,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Space>
        <Segmented
          value={category}
          onChange={(v) => setCategory(v as keyof typeof CATEGORIES)}
          options={Object.entries(CATEGORIES).map(([value, l]) => ({ value, label: l }))}
        />
        {can("reason_code.create") && (
          <Button type="primary" onClick={() => setCreating(true)}>
            New {label.toLowerCase().replace(/s$/, "")}
          </Button>
        )}
      </Space>
      <Table<ReasonCode>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "Code", dataIndex: "code" },
          { title: "Name", dataIndex: "name" },
          { title: "ERP transaction code", dataIndex: "external_code" },
          { title: "Active", dataIndex: "is_active", render: (v: boolean) => <YesNo value={v} /> },
        ]}
      />
      <CreateModal
        key={category}
        open={creating}
        title={`New ${label.toLowerCase().replace(/s$/, "")}`}
        path="/reason-codes"
        queryKey="reason-codes"
        initialValues={{ category }}
        onClose={() => setCreating(false)}
      >
        {() => (
          <>
            <Form.Item name="category" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="code" label="Code" rules={[{ required: true }]}>
              <Input maxLength={30} />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item name="external_code" label="ERP transaction code (when integrating with an ERP)">
              <Input maxLength={50} />
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
