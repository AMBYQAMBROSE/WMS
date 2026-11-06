import { useEffect, useRef } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, DatePicker, Form, Input, InputNumber, Row, Tooltip, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { CustomerSelect, ItemSelect, SupplierSelect, UomSelect } from "@/components/selects";
import { DetailSkeleton, DocTitle, FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

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
  const unsaved = useUnsavedChanges();

  // Fill the form once per source document, not on every refetch (live updates, window focus): that would wipe the user's edits
  const filledFrom = useRef<string>(undefined);
  // The version the form was filled from: live updates refresh `existing` while the user edits, and sending its
  // current version would defeat the server's check for changes made by someone else in the meantime
  const filledVersion = useRef<number>(undefined);
  useEffect(() => {
    if (existing && filledFrom.current !== existing.id) {
      filledFrom.current = existing.id;
      filledVersion.current = existing.row_version;
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
        ? await apiClient.put<Document>(`/${path}/${id}`, { ...body, row_version: filledVersion.current })
        : await apiClient.post<Document>(`/${path}`, body);
      return response.data;
    },
    onSuccess: (doc) => {
      unsaved.reset();
      message.success("Saved");
      queryClient.invalidateQueries({ queryKey: [path] });
      navigate(`/${path}/${doc.id}`);
    },
    onError: showError,
  });

  if (id && isLoading) return <DetailSkeleton />;
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
        {...unsaved.formProps}
      >
        <FormSection title="Order details" description={`Who the order is ${kind === "purchase" ? "from" : "for"} and when it is due.`}>
        <Row gutter={16}>
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
        </FormSection>

        <FormSection title="Lines" description="Quantities are in the unit chosen on each line; the item's base unit is filled in for you.">
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
                      <InputNumber placeholder="0" min={0.0001} style={{ width: "100%" }} aria-label={`Quantity, line ${index + 1}`} />
                    </Form.Item>
                    <Tooltip title="Remove line">
                      <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(name)} disabled={fields.length === 1} aria-label={`Remove line ${index + 1}`} />
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
        </FormSection>

        <FormFooter note={id ? undefined : "Saved as a draft; confirm it from the order page"}>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Save
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
