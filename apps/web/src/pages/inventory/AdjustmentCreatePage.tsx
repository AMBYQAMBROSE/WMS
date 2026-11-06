import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Radio, Row, Table, Tooltip, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit } from "@/components/documents";
import { ItemSelect, LocationSelect, ReasonSelect, UomSelect, useItemRecords } from "@/components/selects";
import { FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

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
  const unsaved = useUnsavedChanges();

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
      unsaved.reset();
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
        {...unsaved.formProps}
      >
        <FormSection title="Reason" description="Every adjustment needs a reason; it is posted only after approval.">
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="reason_code_id" label="Adjustment reason" rules={[{ required: true }]}>
                <ReasonSelect style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={16}>
              <Form.Item name="remark" label="Remark">
                <Input maxLength={400} placeholder="Optional" />
              </Form.Item>
            </Col>
          </Row>
        </FormSection>
        <FormSection title="Lines" description="Choose Increase or Decrease per line, then the quantity (always positive).">
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
                    title: "",
                    width: 48,
                    render: (_, f) => (
                      <Tooltip title="Remove line">
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label={`Remove line ${f.name + 1}`} onClick={() => remove(f.name)} disabled={fields.length === 1} />
                      </Tooltip>
                    ),
                  },
                ]}
              />
              <Button type="dashed" block icon={<PlusOutlined />} style={{ marginTop: 12 }} onClick={() => add(NEW_LINE)}>
                Add line
              </Button>
            </>
          )}
        </Form.List>
        </FormSection>
        <FormFooter note="Takes effect once someone with approval rights posts it">
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Create adjustment
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
