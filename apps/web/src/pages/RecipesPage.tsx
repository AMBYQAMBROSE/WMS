import { useState } from "react";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Col, Descriptions, Drawer, Form, Input, InputNumber, Popconfirm, Row, Space, Table, Tooltip, Typography, message } from "antd";
import { useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Recipe, RecipeCosting } from "@/api/types";
import CreateModal from "@/components/CreateModal";
import MasterSearch from "@/components/MasterSearch";
import { BaseQtyHint, ItemSelect, UomSelect, useItemRecords } from "@/components/selects";
import { DetailSkeleton, FormSection, Pill, STICKY_HEADER, YesNo, emptyLocale, formatPrice, formatQty } from "@/components/ui";

interface LineValues {
  item_id?: string;
  uom_id?: string;
  qty?: number;
}
interface RecipeValues {
  code: string;
  name: string;
  product_item_id: string;
  output_qty: number;
  remark?: string;
  is_active: boolean;
  lines: LineValues[];
}

/** Component lines: item, unit (base or a packing unit of the item) and quantity per batch */
function RecipeLines() {
  const form = Form.useFormInstance<RecipeValues>();
  const lines = Form.useWatch("lines", form) as LineValues[] | undefined;
  const items = useItemRecords(lines?.map((l) => l?.item_id) ?? []);
  const itemOf = (i: number) => items.find((it) => it.id === lines?.[i]?.item_id);
  return (
    <Form.List name="lines" rules={[{ validator: async (_, v) => { if (!v?.length) throw new Error("Add at least one component"); } }]}>
      {(fields, { add, remove }, { errors }) => (
        <>
          {fields.map(({ key, name }, index) => (
            <Row key={key} gutter={8} wrap={false} align="top">
              <Col flex="auto">
                <Form.Item name={[name, "item_id"]} rules={[{ required: true, message: "Choose a component" }]}>
                  <ItemSelect
                    placeholder="Component (SKU or name)"
                    style={{ width: "100%" }}
                    onRecordChange={(item) => item && form.setFieldValue(["lines", name, "uom_id"], item.base_uom_id)}
                  />
                </Form.Item>
              </Col>
              <Col flex="110px">
                <Form.Item name={[name, "uom_id"]} rules={[{ required: true, message: "Unit" }]}>
                  <UomSelect item={itemOf(name)} placeholder="Unit" style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col flex="130px">
                <Form.Item
                  name={[name, "qty"]}
                  rules={[{ required: true, message: "Quantity" }]}
                  extra={<BaseQtyHint item={itemOf(name)} uomId={lines?.[name]?.uom_id} qty={lines?.[name]?.qty} />}
                >
                  <InputNumber min={0.0001} placeholder="Qty" style={{ width: "100%" }} aria-label={`Quantity, component ${index + 1}`} />
                </Form.Item>
              </Col>
              <Col flex="none">
                <Tooltip title="Remove component">
                  <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(name)} disabled={fields.length === 1} aria-label={`Remove component ${index + 1}`} />
                </Tooltip>
              </Col>
            </Row>
          ))}
          <Form.ErrorList errors={errors} />
          <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({})}>
            Add component
          </Button>
        </>
      )}
    </Form.List>
  );
}

/** Cost build-up and what stock can make, for one recipe */
function CostingDrawer({ recipe, onClose }: { recipe: Recipe | undefined; onClose: () => void }) {
  const can = useCan();
  const showCosts = can("cost.view");
  const { data, isLoading } = useQuery({
    queryKey: ["recipes", "costing", recipe?.id],
    queryFn: async () => (await apiClient.get<RecipeCosting>(`/recipes/${recipe!.id}/costing`)).data,
    enabled: !!recipe,
  });
  type Line = RecipeCosting["lines"][number];
  return (
    <Drawer open={!!recipe} onClose={onClose} size="large" title={recipe ? `${recipe.code} · ${recipe.name}` : ""} destroyOnHidden>
      {!recipe || isLoading || !data ? (
        <DetailSkeleton />
      ) : (
        <Space orientation="vertical" style={{ width: "100%" }} size="middle">
          <Descriptions column={{ xs: 1, sm: 2 }} size="small">
            <Descriptions.Item label="Product">
              <span className="wms-mono">{recipe.product.sku_code}</span>&nbsp;{recipe.product.name}
            </Descriptions.Item>
            <Descriptions.Item label="Batch makes">
              {formatQty(recipe.output_qty)} {recipe.product.base_uom.code}
            </Descriptions.Item>
            {showCosts && (
              <>
                <Descriptions.Item label={`Cost per ${recipe.product.base_uom.code}`}>
                  <strong className="wms-num">{formatPrice(data.unit_cost)}</strong>
                </Descriptions.Item>
                <Descriptions.Item label="Cost per batch">{formatPrice(data.batch_cost)}</Descriptions.Item>
              </>
            )}
            <Descriptions.Item label="Current stock can make">
              <strong className="wms-num" data-testid="recipe-can-make">
                {formatQty(data.can_make)} {recipe.product.base_uom.code}
              </strong>
            </Descriptions.Item>
            <Descriptions.Item label="Limited by">
              {data.bottleneck ? (
                <>
                  <span className="wms-mono">{data.bottleneck.sku_code}</span>&nbsp;{data.bottleneck.name}
                </>
              ) : (
                "—"
              )}
            </Descriptions.Item>
          </Descriptions>
          {showCosts && !data.complete && (
            <Alert
              type="warning"
              showIcon
              title={`No purchase price yet for ${data.missing_costs.join(", ")}: the cost covers only the other components. Enter unit prices on purchase orders to complete it.`}
            />
          )}
          <Table<Line>
            size="small"
            rowKey="line_no"
            dataSource={data.lines}
            pagination={false}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "Component", render: (_, l) => <><span className="wms-mono">{l.item.sku_code}</span> {l.item.name}</> },
              { title: "Per batch", align: "right", render: (_, l) => `${formatQty(l.qty)} ${l.uom.code}` },
              { title: `Per ${recipe.product.base_uom.code}`, align: "right", render: (_, l) => `${formatQty(l.qty_per_unit)} ${l.item.base_uom.code}` },
              ...(showCosts
                ? [
                    {
                      title: "Unit cost",
                      align: "right" as const,
                      render: (_: unknown, l: Line) => (
                        <Tooltip title={l.cost_source === "purchase" ? "Latest purchase price" : l.cost_source ? `From ${l.cost_source}` : "No price yet"}>
                          <span className="wms-num">{formatPrice(l.unit_cost)}</span>
                        </Tooltip>
                      ),
                    },
                    { title: "Cost / unit", align: "right" as const, render: (_: unknown, l: Line) => <span className="wms-num">{formatPrice(l.cost_per_unit)}</span> },
                    {
                      title: "Share",
                      render: (_: unknown, l: Line) =>
                        l.share_pct === null ? "—" : (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, minWidth: 110 }}>
                            <span style={{ width: 60, height: 6, borderRadius: 3, background: "var(--ant-color-fill-secondary)", overflow: "hidden" }} aria-hidden>
                              <span style={{ display: "block", height: "100%", width: `${Math.min(100, l.share_pct)}%`, background: "#2a78d6", borderRadius: 3 }} />
                            </span>
                            <span className="wms-num">{l.share_pct}%</span>
                          </span>
                        ),
                    },
                  ]
                : []),
              { title: "Available", align: "right", render: (_, l) => `${formatQty(l.available)} ${l.item.base_uom.code}` },
              {
                title: "Enough for",
                align: "right",
                render: (_, l) =>
                  l.can_make === null ? "—" : (
                    <span className="wms-num">
                      {formatQty(l.can_make)}
                      {data.bottleneck?.id === l.item.id && <> <Pill tone="amber">limit</Pill></>}
                    </span>
                  ),
              },
            ]}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Costs use each component's latest purchase price (excluding tax); a component that is itself made from a recipe is costed from that recipe.
            Available = on hand minus allocated across all locations.
          </Typography.Text>
        </Space>
      )}
    </Drawer>
  );
}

export default function RecipesPage() {
  const can = useCan();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [keyword, setKeyword] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Recipe | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["recipes", "list", keyword],
    queryFn: async () => (await apiClient.get<Recipe[]>("/recipes", { params: { keyword: keyword || undefined } })).data,
  });
  const openId = params.get("open");
  const opened = data?.find((r) => r.id === openId);
  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/recipes/${id}`),
    onSuccess: () => {
      message.success("Deleted");
      void queryClient.invalidateQueries({ queryKey: ["recipes"] });
    },
    onError: showError,
  });
  const manage = can("recipe.manage");

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <MasterSearch
        placeholder="Code / name"
        onSearch={setKeyword}
        shown={data?.length}
        actions={
          manage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
              New recipe
            </Button>
          )
        }
      />
      <Table<Recipe>
        rowKey="id"
        loading={isLoading}
        sticky={STICKY_HEADER}
        scroll={{ x: "max-content" }}
        dataSource={data}
        locale={emptyLocale("No recipes yet. A recipe lists the components that make a product, for costing and to see how much stock can make.")}
        pagination={{ pageSize: 50, showSizeChanger: true }}
        columns={[
          { title: "Code", dataIndex: "code", render: (v: string, r) => <a onClick={() => setParams({ open: r.id })} className="wms-mono">{v}</a> },
          { title: "Name", dataIndex: "name" },
          { title: "Product", render: (_, r) => <><span className="wms-mono">{r.product.sku_code}</span> {r.product.name}</> },
          { title: "Batch makes", align: "right", render: (_, r) => `${formatQty(r.output_qty)} ${r.product.base_uom.code}` },
          { title: "Components", align: "right", render: (_, r) => r.lines.length },
          { title: "Active", dataIndex: "is_active", render: (v: boolean) => <YesNo value={v} /> },
          {
            title: "",
            key: "actions",
            render: (_, r) => (
              <Space size={4}>
                <Button size="small" onClick={() => setParams({ open: r.id })}>
                  Costing
                </Button>
                {manage && (
                  <>
                    <Button size="small" onClick={() => setEditing(r)}>
                      Edit
                    </Button>
                    <Popconfirm title={`Delete recipe ${r.code}?`} onConfirm={() => remove.mutate(r.id)}>
                      <Button size="small" danger icon={<DeleteOutlined />} aria-label={`Delete recipe ${r.code}`} />
                    </Popconfirm>
                  </>
                )}
              </Space>
            ),
          },
        ]}
      />
      <CostingDrawer recipe={opened} onClose={() => setParams({})} />
      <CreateModal<RecipeValues>
        open={creating || editing !== null}
        title={editing ? `Edit recipe: ${editing.code}` : "New recipe"}
        path="/recipes"
        queryKey="recipes"
        record={editing}
        initialValues={
          editing
            ? {
                code: editing.code, name: editing.name, product_item_id: editing.product.id, output_qty: editing.output_qty,
                remark: editing.remark ?? undefined, is_active: editing.is_active,
                lines: editing.lines.map((l) => ({ item_id: l.item.id, uom_id: l.uom.id, qty: l.qty })),
              }
            : { output_qty: 1, is_active: true, lines: [{}] }
        }
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
      >
        {() => (
          <>
            <Row gutter={12}>
              <Col xs={24} sm={8}>
                <Form.Item name="code" label="Code" rules={[{ required: true }]} extra={editing ? "Cannot be changed" : undefined}>
                  <Input disabled={!!editing} maxLength={50} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={16}>
                <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                  <Input maxLength={200} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={16}>
                <Form.Item name="product_item_id" label="Product made" rules={[{ required: true }]}>
                  <ItemSelect placeholder="Finished product" style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={8}>
                <Form.Item name="output_qty" label="Batch makes" rules={[{ required: true }]} extra="In the product's base unit">
                  <InputNumber min={0.0001} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
            <FormSection title="Components" description="What one batch uses. Quantities may be in a component's base unit or a packing unit set up on it.">
              <RecipeLines />
            </FormSection>
            <Form.Item name="remark" label="Remark">
              <Input maxLength={400} placeholder="Optional" />
            </Form.Item>
            <Form.Item name="is_active" valuePropName="checked">
              <Checkbox>Active (shown on the dashboard)</Checkbox>
            </Form.Item>
          </>
        )}
      </CreateModal>
    </Space>
  );
}
