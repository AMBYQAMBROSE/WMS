import { useState } from "react";

import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Form, Input, Select, Space, Table } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { Location } from "@/api/types";
import MasterSearch, { MASTER_LIST_LIMIT } from "@/components/MasterSearch";
import { YesNo } from "@/components/ui";
import CreateModal from "@/components/CreateModal";
import { LocationSelect } from "@/components/selects";
import { LOCATION_TYPE_LABELS } from "@/constants/labels";

const yesNo = (v: boolean) => <YesNo value={v} />;

export default function LocationsPage() {
  const can = useCan();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["locations", keyword],
    queryFn: async () => (await apiClient.get<Location[]>("/locations", { params: { limit: MASTER_LIST_LIMIT, keyword: keyword || undefined } })).data,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <MasterSearch
        placeholder="Location code / name" onSearch={setKeyword} shown={data?.length}
        actions={
          can("location.create") && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
              New location
            </Button>
          )
        }
      />
      <Table<Location>
        rowKey="id"
        loading={isLoading}
        dataSource={data}
        columns={[
          { title: "Code", dataIndex: "code" },
          { title: "Name", dataIndex: "name" },
          { title: "Type", dataIndex: "location_type", render: (v: string) => LOCATION_TYPE_LABELS[v] ?? v },
          { title: "Path", dataIndex: "path" },
          { title: "Pickable", dataIndex: "is_pickable", render: yesNo },
          { title: "Locked", dataIndex: "is_locked", render: yesNo },
        ]}
      />
      <CreateModal
        open={creating}
        title="New location"
        path="/locations"
        queryKey="locations"
        initialValues={{ location_type: "BIN", is_pickable: false, is_locked: false }}
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
            <Form.Item name="location_type" label="Type" rules={[{ required: true }]}>
              <Select
                options={Object.entries(LOCATION_TYPE_LABELS).map(([value, label]) => ({
                  value,
                  label: `${label} (${value})`,
                }))}
              />
            </Form.Item>
            <Form.Item name="parent_id" label="Parent location">
              <LocationSelect allowClear placeholder="Leave empty for a top-level location" />
            </Form.Item>
            <Form.Item name="is_pickable" valuePropName="checked">
              <Checkbox>Pickable</Checkbox>
            </Form.Item>
            <Form.Item name="is_locked" valuePropName="checked">
              <Checkbox>Locked</Checkbox>
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
