import { useEffect } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, DatePicker, Form, Input, InputNumber, Row, Spin, Tooltip, Typography, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { CustomerSelect, ItemSelect, SupplierSelect, UomSelect } from "@/components/selects";
import { DocTitle, FormFooter } from "@/components/ui";

interface LineValues {
  item_id: string;
  uom_id: string;
  qty: number;
}

interface FormValues {
  partner_id: string;
  expected_date?: Dayjs;
  remark?: string;
  lines: LineValues[];
}

const KINDS = {
  purchase: { path: "purchase-orders", docLabel: "Purchase order", partnerLabel: "Supplier", dateLabel: "Expected arrival date", Partner: SupplierSelect },
  sales: { path: "sales-orders", docLabel: "Sales order", partnerLabel: "Customer", dateLabel: "Requested ship date", Partner: CustomerSelect },
} as const;

/** Create/edit form shared by purchase and sales orders: same structure, only the partner (supplier/customer) and wording differ */
export default function OrderForm({ kind }: { kind: keyof typeof KINDS }) {
  const { path, docLabel, partnerLabel, dateLabel, Partner } = KINDS[kind];
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const { data: existing, isLoading } = useDocument(path, id);

  useEffect(() => {
    if (existing) {
      form.setFieldsValue({
        partner_id: existing.partner?.id,
        expected_date: existing.expected_date ? dayjs(existing.expected_date) : undefined,
        remark: existing.remark ?? undefined,
        lines: existing.lines.map((l) => ({ item_id: l.item.id, uom_id: l.uom.id, qty: l.qty_planned })),
      });
    }
  }, [existing, form]);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const body = { ...values, expected_date: values.expected_date?.format("YYYY-MM-DD") ?? null };
      const response = id
        ? await apiClient.put<Document>(`/${path}/${id}`, body)
        : await apiClient.post<Document>(`/${path}`, body);
      return response.data;
    },
    onSuccess: (doc) => {
      message.success("Saved");
      queryClient.invalidateQueries({ queryKey: [path] });
      navigate(`/${path}/${doc.id}`);
    },
    onError: showError,
  });

  if (id && isLoading) return <Spin />;
  if (existing && existing.status !== "DRAFT") {
    return <Alert type="warning" title={`${docLabel} ${existing.doc_no} is no longer a draft and cannot be edited`} />;
  }

  return (
    <Card title={id ? <DocTitle label={`Edit ${docLabel.toLowerCase()}`} no={existing?.doc_no ?? ""} /> : `New ${docLabel.toLowerCase()}`}>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(values) => save.mutate(values)}
      >
        <Row gutter={20}>
          <Col xs={24} md={10}>
            <Form.Item name="partner_id" label={partnerLabel} rules={[{ required: true }]}>
              <Partner style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item name="expected_date" label={dateLabel}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="remark" label="Remark">
              <Input maxLength={400} placeholder="Optional" />
            </Form.Item>
          </Col>
        </Row>

        <Typography.Title level={5} style={{ margin: "4px 0 12px" }}>
          Lines
        </Typography.Title>
        <Form.List
          name="lines"
          rules={[
            {
              validator: async (_, lines) => {
                if (!lines?.length) throw new Error("At least one line is required");
              },
            },
          ]}
        >
          {(fields, { add, remove }, { errors }) => (
            <>
              <div className="wms-lines">
                <div className="wms-lines-head">
                  <span>#</span>
                  <span>Item</span>
                  <span>Unit</span>
                  <span>Quantity</span>
                  <span />
                </div>
                {fields.map(({ key, name }, index) => (
                  <div key={key} className="wms-lines-row">
                    <span className="wms-lines-no">{index + 1}</span>
                    <Form.Item name={[name, "item_id"]} rules={[{ required: true, message: "Choose an item" }]}>
                      <ItemSelect
                        placeholder="Search SKU or name"
                        style={{ width: "100%" }}
                        onRecordChange={(item) => item && form.setFieldValue(["lines", name, "uom_id"], item.base_uom_id)}
                      />
                    </Form.Item>
                    <Form.Item name={[name, "uom_id"]} rules={[{ required: true, message: "Choose a unit" }]}>
                      <UomSelect placeholder="Unit" style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name={[name, "qty"]} rules={[{ required: true, message: "Enter a quantity" }]}>
                      <InputNumber placeholder="0" min={0.0001} style={{ width: "100%" }} />
                    </Form.Item>
                    <Tooltip title="Remove line">
                      <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(name)} disabled={fields.length === 1} aria-label="Delete" />
                    </Tooltip>
                  </div>
                ))}
              </div>
              <Form.ErrorList errors={errors} />
              <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add()}>
                Add line
              </Button>
            </>
          )}
        </Form.List>

        <FormFooter>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Save
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
