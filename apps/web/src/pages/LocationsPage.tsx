import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Form, Input, Select, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { Location } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import { LocationSelect } from "@/components/selects";
import { LOCATION_TYPE_LABELS } from "@/constants/labels";

const yesNo = (v: boolean) => (v ? "是" : "否");

export default function LocationsPage() {
  const [creating, setCreating] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["locations"],
    queryFn: async () => (await apiClient.get<Location[]>("/locations", { params: { limit: 500 } })).data,
  });

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Button type="primary" onClick={() => setCreating(true)}>
        新建仓位
      </Button>
      <Table<Location>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "编码", dataIndex: "code" },
          { title: "名称", dataIndex: "name" },
          { title: "类型", dataIndex: "location_type", render: (v: string) => LOCATION_TYPE_LABELS[v] ?? v },
          { title: "路径", dataIndex: "path" },
          { title: "可拣货", dataIndex: "is_pickable", render: yesNo },
          { title: "锁定", dataIndex: "is_locked", render: yesNo },
        ]}
      />
      <CreateModal
        open={creating}
        title="新建仓位"
        path="/locations"
        queryKey="locations"
        initialValues={{ location_type: "BIN", is_pickable: false, is_locked: false }}
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
            <Form.Item name="location_type" label="类型" rules={[{ required: true }]}>
              <Select
                options={Object.entries(LOCATION_TYPE_LABELS).map(([value, label]) => ({
                  value,
                  label: `${label}（${value}）`,
                }))}
              />
            </Form.Item>
            <Form.Item name="parent_id" label="上级仓位">
              <LocationSelect allowClear placeholder="不选则为顶层" />
            </Form.Item>
            <Form.Item name="is_pickable" valuePropName="checked">
              <Checkbox>可拣货</Checkbox>
            </Form.Item>
            <Form.Item name="is_locked" valuePropName="checked">
              <Checkbox>锁定</Checkbox>
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
