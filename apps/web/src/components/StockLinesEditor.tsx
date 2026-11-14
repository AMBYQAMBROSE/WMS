import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, DatePicker, Form, Input, InputNumber, Radio, Table } from "antd";
import type { FormInstance } from "antd";

import { BaseQtyHint, LocationSelect, UomSelect, useItemRecords } from "@/components/selects";
import { StockItemSelect, useStockAutofill } from "@/components/stockAutofill";

/**
 * Line editor shared by customer returns, returns to supplier and repacks: item, unit, quantity, location, batch/expiry (shown per item settings).
 * withDisposition: customer returns only; each line chooses restock or scrap, and scrap lines need no location, batch or expiry.
 * stockSource: the lines take stock out of their location (return to supplier, repack consumption). The location then
 * comes first: choosing it fills the item, batch, expiry and free quantity found there, and the item dropdown offers
 * what that location holds.
 */
export default function StockLinesEditor({
  form,
  name,
  locationLabel,
  locationTypes = ["BIN", "DOCK"],
  withDisposition = false,
  stockSource = false,
  testId,
}: {
  form: FormInstance;
  name: string;
  locationLabel: string;
  locationTypes?: string[];
  withDisposition?: boolean;
  stockSource?: boolean;
  testId?: string;
}) {
  const lines = Form.useWatch(name, form) as { item_id?: string; uom_id?: string; qty?: number; disposition?: string; location_id?: string }[] | undefined;
  const autofill = useStockAutofill(form);
  const items = useItemRecords(lines?.map((l) => l?.item_id) ?? []);
  const itemOf = (i: number) => items?.find((it) => it.id === lines?.[i]?.item_id);
  const restock = (i: number) => !withDisposition || lines?.[i]?.disposition !== "SCRAP";

  // First column when the lines take stock out of the location (it then fills the rest of the line), after the quantity otherwise
  const locationColumn = {
    title: locationLabel,
    render: (_: unknown, f: { name: number }) =>
      restock(f.name) ? (
        <Form.Item name={[f.name, "location_id"]} noStyle rules={[{ required: true, message: "Required" }]}>
          <LocationSelect
            types={locationTypes}
            style={{ width: 170 }}
            onRecordChange={() => stockSource && void autofill([name, f.name], { source: true, locationChanged: true })}
          />
        </Form.Item>
      ) : (
        <span className="wms-empty-value">Not stocked</span>
      ),
  };

  return (
    <Form.List name={name}>
      {(fields, { add, remove }) => (
        <>
          <Table
            rowKey="key"
            size="small"
            pagination={false}
            dataSource={fields}
            scroll={{ x: true }}
            data-testid={testId}
            columns={[
              ...(stockSource ? [locationColumn] : []),
              {
                title: "Item",
                render: (_: unknown, f: { name: number }) => (
                  <Form.Item name={[f.name, "item_id"]} noStyle rules={[{ required: true }]}>
                    <StockItemSelect
                      style={{ width: 220 }}
                      locationId={stockSource ? lines?.[f.name]?.location_id : undefined}
                      onRecordChange={(item) => {
                        if (!item) return;
                        form.setFieldValue([name, f.name, "uom_id"], item.base_uom_id);
                        if (stockSource) void autofill([name, f.name], { source: true });
                      }}
                    />
                  </Form.Item>
                ),
              },
              {
                title: "Unit",
                render: (_, f) => (
                  <Form.Item name={[f.name, "uom_id"]} noStyle rules={[{ required: true }]}>
                    <UomSelect item={itemOf(f.name)} style={{ width: 120 }} />
                  </Form.Item>
                ),
              },
              {
                title: "Quantity",
                render: (_, f) => (
                  <>
                    <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                      <InputNumber min={0.0001} aria-label={`Quantity, line ${f.name + 1}`} />
                    </Form.Item>
                    <BaseQtyHint item={itemOf(f.name)} uomId={lines?.[f.name]?.uom_id} qty={lines?.[f.name]?.qty} />
                  </>
                ),
              },
              ...(withDisposition
                ? [
                    {
                      title: "Disposition",
                      render: (_: unknown, f: { name: number }) => (
                        <Form.Item name={[f.name, "disposition"]} noStyle>
                          <Radio.Group optionType="button" buttonStyle="solid">
                            <Radio value="RESTOCK">Restock</Radio>
                            <Radio value="SCRAP">Scrap</Radio>
                          </Radio.Group>
                        </Form.Item>
                      ),
                    },
                  ]
                : []),
              ...(stockSource ? [] : [locationColumn]),
              {
                title: "Batch no.",
                render: (_, f) =>
                  itemOf(f.name)?.is_batch_managed && restock(f.name) ? (
                    <Form.Item name={[f.name, "batch_no"]} noStyle rules={[{ required: true }]}>
                      <Input style={{ width: 110 }} />
                    </Form.Item>
                  ) : (
                    "-"
                  ),
              },
              {
                title: "Expiry date",
                render: (_, f) =>
                  itemOf(f.name)?.is_expiry_managed && restock(f.name) ? (
                    <Form.Item name={[f.name, "expiry_date"]} noStyle rules={[{ required: true }]}>
                      <DatePicker />
                    </Form.Item>
                  ) : (
                    "-"
                  ),
              },
              {
                title: "",
                width: 48,
                render: (_, f) => (
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => remove(f.name)} disabled={fields.length === 1} aria-label={`Remove line ${f.name + 1}`} />
                ),
              },
            ]}
          />
          <Button type="dashed" block icon={<PlusOutlined />} style={{ marginTop: 12 }} onClick={() => add(withDisposition ? { disposition: "RESTOCK" } : {})}>
            Add line
          </Button>
        </>
      )}
    </Form.List>
  );
}

/** Convert dayjs dates and empty batches in the form to the API format */
export function toLinePayload<T extends { batch_no?: string; expiry_date?: { format: (f: string) => string } }>(
  line: T,
) {
  return {
    ...line,
    batch_no: line.batch_no || null,
    expiry_date: line.expiry_date?.format("YYYY-MM-DD") ?? null,
  };
}
