import { useState } from "react";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Col, Form, Input, InputNumber, Row, Select, Space, Table, Tooltip } from "antd";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { Item } from "@/api/types";
import MasterSearch, { MASTER_LIST_LIMIT } from "@/components/MasterSearch";
import { useColumnPrefs } from "@/components/ListTools";
import { FormSection, STICKY_HEADER, YesNo } from "@/components/ui";
import CreateModal from "@/components/CreateModal";
import { useMasterActionsColumn } from "@/components/MasterRowActions";
import { UomSelect, useUoms } from "@/components/selects";
import { PrintLabelsButton, PrintLabelsModal } from "@/components/labels";

const yesNo = (v: boolean) => <YesNo value={v} />;

interface PackingValues {
  uom_id?: string;
  factor?: number | null;
}
type ItemFormValues = Partial<Omit<Item, "packings">> & { packings?: PackingValues[] };

/** Units offered on a new item: carton and pallet rows ready for their quantities */
const DEFAULT_PACKING_CODES = ["CTN", "PLT"];

/** Rows without a quantity mean "not packed this way" and are left out */
const withPackings = (values: ItemFormValues) => ({
  ...values,
  packings: (values.packings ?? [])
    .filter((p) => p?.uom_id && p.factor)
    .map((p) => ({ uom_id: p.uom_id, factor: p.factor })),
});

export default function ItemsPage() {
  const can = useCan();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [printing, setPrinting] = useState(false);
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
    {
      title: "Packing",
      key: "packings",
      render: (_: unknown, it: Item) =>
        it.packings?.length ? (
          <span style={{ whiteSpace: "nowrap" }}>
            {it.packings.map((p) => `1 ${p.uom.code} = ${p.factor.toLocaleString()} ${uomCode(it.base_uom_id)}`).join(" · ")}
          </span>
        ) : (
          <span className="wms-empty-value">—</span>
        ),
    },
    { title: "Batch managed", dataIndex: "is_batch_managed", render: yesNo },
    { title: "Expiry managed", dataIndex: "is_expiry_managed", render: yesNo },
    { title: "Active", dataIndex: "is_active", render: yesNo },
  ]);
  const actions = useMasterActionsColumn<Item>({
    permission: "item",
    path: "/items",
    queryKey: "items",
    describe: (it) => `item ${it.sku_code}`,
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
        placeholder="SKU / name / barcode" onSearch={setKeyword} shown={data?.length}
        actions={
          <>
            {columnSettings}
            <PrintLabelsButton disabled={!selected.length} onClick={() => setPrinting(true)}>
              {selected.length ? `Print labels (${selected.length})` : "Print labels"}
            </PrintLabelsButton>
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
        columns={tableColumns}
        // Kept across searches, so items found by several searches can be printed together
        rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]), preserveSelectedRowKeys: true }}
      />
      <PrintLabelsModal
        open={printing}
        purpose="ITEM"
        path="/labels/items"
        body={{ item_ids: selected }}
        maxCopies={500}
        summary={`${selected.length} item${selected.length === 1 ? "" : "s"} selected. Each label carries the item's barcode, or its SKU when it has none; both scan on the PDA.`}
        onClose={() => setPrinting(false)}
      />
      <CreateModal
        open={creating || editing !== null}
        title={editing ? `Edit item: ${editing.sku_code}` : "New item"}
        path="/items"
        queryKey="items"
        record={editing}
        initialValues={
          editing
            ? { ...editing, packings: editing.packings.map((p) => ({ uom_id: p.uom.id, factor: p.factor })) }
            : {
                is_batch_managed: false,
                is_expiry_managed: false,
                packings: DEFAULT_PACKING_CODES.flatMap((code) => {
                  const uom = uoms?.find((u) => u.code === code);
                  return uom ? [{ uom_id: uom.id, factor: null }] : [];
                }),
              }
        }
        transform={withPackings}
        onClose={closeForm}
      >
        {() => (
          <>
            <Row gutter={12}>
              <Col xs={24} sm={10}>
                <Form.Item name="sku_code" label="SKU" rules={[{ required: true }]} extra={editing ? "Cannot be changed" : undefined}>
                  <Input disabled={!!editing} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={14}>
                <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={24} sm={10}>
                <Form.Item name="base_uom_id" label="Base unit" rules={[{ required: true }]}>
                  <UomSelect disabled={!!editing} />
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
            <FormSection
              title="Tracking"
              description={
                editing
                  ? "Batch and expiry tracking are fixed once the item exists, because existing stock was recorded with or without them."
                  : "Batch and expiry tracking cannot be added later without stock adjustments."
              }
            >
              <Form.Item name="is_batch_managed" valuePropName="checked" style={{ marginBottom: 8 }}>
                <Checkbox disabled={!!editing}>Batch managed</Checkbox>
              </Form.Item>
              <Form.Item name="is_expiry_managed" valuePropName="checked">
                <Checkbox disabled={!!editing}>Expiry managed</Checkbox>
              </Form.Item>
              <Form.Item name="shelf_life_days" label="Shelf life (days)">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </FormSection>
            <FormSection
              title="Packing units"
              description="How many base units one carton or pallet holds. Receipts and orders can then be entered in cartons or pallets, and stock is added or taken in base units. Leave a quantity empty if the item is not packed that way. A quantity cannot change once documents use it."
            >
              <Form.Item noStyle dependencies={["base_uom_id"]}>
                {({ getFieldValue }) => {
                  const baseId = getFieldValue("base_uom_id") as string | undefined;
                  const base = baseId ? uomCode(baseId) : "";
                  const options = (uoms ?? []).filter((u) => u.id !== baseId).map((u) => ({ value: u.id, label: `${u.code} ${u.name}` }));
                  return (
                    <Form.List name="packings">
                      {(fields, { add, remove }) => (
                        <>
                          {fields.map((f) => (
                            <Row key={f.key} gutter={8} wrap={false} align="top">
                              <Col flex="170px">
                                <Form.Item
                                  name={[f.name, "uom_id"]}
                                  rules={[
                                    { required: true, message: "Choose a unit" },
                                    {
                                      validator: async (_, value) => {
                                        const all = (getFieldValue("packings") as PackingValues[] | undefined) ?? [];
                                        if (value && all.filter((p) => p?.uom_id === value).length > 1) throw new Error("Listed twice");
                                      },
                                    },
                                  ]}
                                >
                                  <Select showSearch optionFilterProp="label" options={options} placeholder="Unit" aria-label={`Packing unit ${f.name + 1}`} />
                                </Form.Item>
                              </Col>
                              <Col flex="none" style={{ paddingTop: 5 }}>
                                holds
                              </Col>
                              <Col flex="auto">
                                <Form.Item name={[f.name, "factor"]}>
                                  <InputNumber
                                    min={0.0001}
                                    placeholder="Quantity"
                                    suffix={base}
                                    style={{ width: "100%" }}
                                    aria-label={`Base units per packing unit ${f.name + 1}`}
                                  />
                                </Form.Item>
                              </Col>
                              <Col flex="none">
                                <Tooltip title="Remove unit">
                                  <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(f.name)} aria-label={`Remove packing unit ${f.name + 1}`} />
                                </Tooltip>
                              </Col>
                            </Row>
                          ))}
                          <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({})}>
                            Add packing unit
                          </Button>
                        </>
                      )}
                    </Form.List>
                  );
                }}
              </Form.Item>
            </FormSection>
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
