import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, DatePicker, Form, Input, InputNumber, Radio, Space, Table, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit } from "@/components/documents";
import { ItemSelect, LocationSelect, ReasonSelect, UomSelect, useItemRecords } from "@/components/selects";
import { FormFooter } from "@/components/ui";

interface LineValues {
  location_id?: string;
  item_id?: string;
  uom_id?: string;
  direction: 1 | -1;
  qty?: number;
  batch_no?: string;
  expiry_date?: Dayjs;
}

interface FormValues {
  reason_code_id: string;
  remark?: string;
  lines: LineValues[];
}

const NEW_LINE: LineValues = { direction: -1 };

export default function AdjustmentCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const watchedLines = Form.useWatch("lines", form);
  const items = useItemRecords(watchedLines?.map((l) => l?.item_id) ?? []);
  const itemOf = (index: number) => items?.find((i) => i.id === watchedLines?.[index]?.item_id);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const lines = values.lines.map(({ direction, qty, ...l }) => ({
        ...l,
        // The UI picks increase/decrease separately to avoid mistyped minus signs; the API takes signed quantities
        qty: (qty ?? 0) * direction,
        batch_no: l.batch_no || null,
        expiry_date: l.expiry_date?.format("YYYY-MM-DD") ?? null,
      }));
      return (await apiClient.post<Document>("/adjustments", { ...values, lines })).data;
    },
    onSuccess: (doc) => {
      message.success(`Created adjustment ${doc.doc_no}; it takes effect once someone with approval rights posts it`);
      queryClient.invalidateQueries({ queryKey: ["adjustments"] });
      navigate(`/adjustments/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="New stock adjustment">
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [NEW_LINE] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
      >
        <Space size="large" wrap>
          <Form.Item name="reason_code_id" label="Adjustment reason" rules={[{ required: true }]}>
            <ReasonSelect style={{ width: 240 }} />
          </Form.Item>
          <Form.Item name="remark" label="Remark">
            <Input style={{ width: 360 }} maxLength={400} />
          </Form.Item>
        </Space>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <>
              <Table
                rowKey="key"
                size="small"
                pagination={false}
                dataSource={fields}
                scroll={{ x: true }}
                columns={[
                  {
                    title: "Location",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "location_id"]} noStyle rules={[{ required: true }]}>
                        <LocationSelect types={["BIN", "DOCK"]} style={{ width: 170 }} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Item",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "item_id"]} noStyle rules={[{ required: true }]}>
                        <ItemSelect
                          style={{ width: 220 }}
                          onRecordChange={(item) => item && form.setFieldValue(["lines", f.name, "uom_id"], item.base_uom_id)}
                        />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Unit",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "uom_id"]} noStyle rules={[{ required: true }]}>
                        <UomSelect style={{ width: 100 }} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Direction",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "direction"]} noStyle>
                        <Radio.Group optionType="button" buttonStyle="solid">
                          <Radio value={1}>Increase</Radio>
                          <Radio value={-1}>Decrease</Radio>
                        </Radio.Group>
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Quantity",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                        <InputNumber min={0.0001} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Batch no.",
                    render: (_, f) =>
                      itemOf(f.name)?.is_batch_managed ? (
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
                      itemOf(f.name)?.is_expiry_managed ? (
                        <Form.Item name={[f.name, "expiry_date"]} noStyle rules={[{ required: true }]}>
                          <DatePicker />
                        </Form.Item>
                      ) : (
                        "-"
                      ),
                  },
                  {
                    title: "Actions",
                    render: (_, f) => (
                      <Button size="small" onClick={() => remove(f.name)} disabled={fields.length === 1}>
                        Remove
                      </Button>
                    ),
                  },
                ]}
              />
              <Button type="dashed" style={{ marginTop: 8 }} onClick={() => add(NEW_LINE)}>
                Add line
              </Button>
            </>
          )}
        </Form.List>
        <FormFooter>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Create adjustment
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
