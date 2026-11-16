import { useState } from "react";

import { DownOutlined, PlusOutlined, PrinterOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Dropdown, Form, Input, Select, Space, Table, Typography } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { Location } from "@/api/types";
import MasterSearch, { MASTER_LIST_LIMIT } from "@/components/MasterSearch";
import { useColumnPrefs } from "@/components/ListTools";
import { Pill, STICKY_HEADER, YesNo } from "@/components/ui";
import CreateModal from "@/components/CreateModal";
import { useMasterActionsColumn } from "@/components/MasterRowActions";
import { LocationSelect } from "@/components/selects";
import { LOCATION_TYPE_LABELS } from "@/constants/labels";
import { PrintLabelsModal } from "@/components/labels";

const yesNo = (v: boolean) => <YesNo value={v} />;

/** Hierarchy levels get distinct but quiet tones; docks (receiving/shipping) stand out */
const TYPE_TONE: Record<string, "indigo" | "blue" | "cyan" | "violet" | "slate" | "amber"> = {
  WAREHOUSE: "indigo",
  ZONE: "violet",
  AISLE: "blue",
  RACK: "cyan",
  BIN: "slate",
  DOCK: "amber",
};

export default function LocationsPage() {
  const can = useCan();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Location | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [printing, setPrinting] = useState<"selected" | "area" | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["locations", keyword],
    queryFn: async () => (await apiClient.get<Location[]>("/locations", { params: { limit: MASTER_LIST_LIMIT, keyword: keyword || undefined } })).data,
  });

  const { columns, settings: columnSettings } = useColumnPrefs<Location>("locations", [
    { title: "Code", dataIndex: "code", render: (v: string) => <span className="wms-mono">{v}</span> },
    { title: "Name", dataIndex: "name" },
    { title: "Type", dataIndex: "location_type", render: (v: string) => <Pill tone={TYPE_TONE[v] ?? "slate"}>{LOCATION_TYPE_LABELS[v] ?? v}</Pill> },
    { title: "Path", dataIndex: "path", render: (v: string) => <Typography.Text type="secondary" className="wms-code">{v}</Typography.Text> },
    { title: "Pickable", dataIndex: "is_pickable", render: yesNo },
    { title: "Locked", dataIndex: "is_locked", render: (v: boolean) => (v ? <Pill tone="red" dot>Locked</Pill> : <YesNo value={false} />) },
  ]);
  const actions = useMasterActionsColumn<Location>({
    permission: "location",
    path: "/locations",
    queryKey: "locations",
    describe: (l) => `location ${l.code}`,
    onEdit: setEditing,
  });
  const tableColumns = actions ? [...columns, actions] : columns;
  const closeForm = () => {
    setCreating(false);
    setEditing(null);
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <MasterSearch
        placeholder="Location code / name" onSearch={setKeyword} shown={data?.length}
        actions={
          <>
            {columnSettings}
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  { key: "selected", label: `Selected locations${selected.length ? ` (${selected.length})` : ""}`, disabled: !selected.length },
                  { key: "area", label: "Every bin and dock in an area…" },
                ],
                onClick: ({ key }) => setPrinting(key as "selected" | "area"),
              }}
            >
              <Button icon={<PrinterOutlined />} data-testid="print-location-labels">
                {selected.length ? `Print labels (${selected.length})` : "Print labels"} <DownOutlined />
              </Button>
            </Dropdown>
            {can("location.create") && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
                New location
              </Button>
            )}
          </>
        }
      />
      <Table<Location>
        rowKey="id"
        loading={isLoading}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (t) => `${t.toLocaleString()} records` }}
        dataSource={data}
        columns={tableColumns}
        rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]), preserveSelectedRowKeys: true }}
      />
      <PrintLabelsModal
        open={printing !== null}
        purpose="LOCATION"
        path="/labels/locations"
        body={printing === "selected" ? { location_ids: selected } : {}}
        maxCopies={20}
        summary={
          printing === "selected"
            ? `${selected.length} location${selected.length === 1 ? "" : "s"} selected.`
            : "Prints every active bin and dock under the chosen location, in code order, so the sheets come out in the order they go on the racks."
        }
        onClose={() => setPrinting(null)}
      >
        {printing === "area" && (
          <Form.Item name="parent_id" label="Area" rules={[{ required: true, message: "Choose a warehouse, zone, aisle or rack" }]}>
            <LocationSelect types={["WAREHOUSE", "ZONE", "AISLE", "RACK"]} placeholder="Warehouse, zone, aisle or rack" />
          </Form.Item>
        )}
      </PrintLabelsModal>
      <CreateModal
        open={creating || editing !== null}
        title={editing ? `Edit location: ${editing.code}` : "New location"}
        path="/locations"
        queryKey="locations"
        record={editing}
        initialValues={editing ?? { location_type: "BIN", is_pickable: false, is_locked: false }}
        onClose={closeForm}
      >
        {() => (
          <>
            <Form.Item name="code" label="Code" rules={[{ required: true }]} extra={editing ? "Cannot be changed" : undefined}>
              <Input disabled={!!editing} />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="location_type" label="Type" rules={[{ required: true }]}>
              <Select
                disabled={!!editing}
                options={Object.entries(LOCATION_TYPE_LABELS).map(([value, label]) => ({
                  value,
                  label: `${label} (${value})`,
                }))}
              />
            </Form.Item>
            {editing ? (
              <Form.Item label="Path" extra="The place in the hierarchy cannot be changed">
                <Typography.Text type="secondary" className="wms-code">{editing.path}</Typography.Text>
              </Form.Item>
            ) : (
              <Form.Item name="parent_id" label="Parent location">
                <LocationSelect allowClear placeholder="Leave empty for a top-level location" />
              </Form.Item>
            )}
            <Form.Item name="is_pickable" valuePropName="checked">
              <Checkbox>Pickable</Checkbox>
            </Form.Item>
            <Form.Item name="is_locked" valuePropName="checked">
              <Checkbox>Locked</Checkbox>
            </Form.Item>
            {editing && (
              <Form.Item name="is_active" valuePropName="checked">
                <Checkbox>Active</Checkbox>
              </Form.Item>
            )}
          </>
        )}
      </CreateModal>
    </Space>
  );
}
