import { useEffect } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Form, Input, InputNumber, Space, Spin, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { ItemSelect, SupplierSelect, UomSelect, useItems } from "@/components/selects";

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

export default function PurchaseOrderFormPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const { data: items } = useItems();
  const { data: existing, isLoading } = useDocument("purchase-orders", id);

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
        ? await apiClient.put<Document>(`/purchase-orders/${id}`, body)
        : await apiClient.post<Document>("/purchase-orders", body);
      return response.data;
    },
    onSuccess: (po) => {
      message.success("已保存");
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      navigate(`/purchase-orders/${po.id}`);
    },
    onError: showError,
  });

  if (id && isLoading) return <Spin />;
  if (existing && existing.status !== "DRAFT") {
    return <Alert type="warning" message={`采购单 ${existing.doc_no} 已不是草稿，不能修改`} />;
  }

  return (
    <Card title={id ? `编辑采购单 ${existing?.doc_no ?? ""}` : "新建采购单"}>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(values) => save.mutate(values)}
      >
        <Space size="large" wrap>
          <Form.Item name="partner_id" label="供应商" rules={[{ required: true }]}>
            <SupplierSelect style={{ width: 280 }} />
          </Form.Item>
          <Form.Item name="expected_date" label="预计到货日期">
            <DatePicker />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input style={{ width: 320 }} maxLength={400} />
          </Form.Item>
        </Space>

        <Form.List
          name="lines"
          rules={[
            {
              validator: async (_, lines) => {
                if (!lines?.length) throw new Error("至少需要一行明细");
              },
            },
          ]}
        >
          {(fields, { add, remove }, { errors }) => (
            <>
              {fields.map(({ key, name }) => (
                <Space key={key} align="baseline" wrap>
                  <Form.Item name={[name, "item_id"]} rules={[{ required: true, message: "请选择商品" }]}>
                    <ItemSelect
                      placeholder="商品"
                      style={{ width: 300 }}
                      onChange={(itemId) => {
                        const item = items?.find((i) => i.id === itemId);
                        if (item) form.setFieldValue(["lines", name, "uom_id"], item.base_uom_id);
                      }}
                    />
                  </Form.Item>
                  <Form.Item name={[name, "uom_id"]} rules={[{ required: true, message: "请选择单位" }]}>
                    <UomSelect placeholder="单位" style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name={[name, "qty"]} rules={[{ required: true, message: "请输入数量" }]}>
                    <InputNumber placeholder="数量" min={0.0001} />
                  </Form.Item>
                  <Button onClick={() => remove(name)} disabled={fields.length === 1}>
                    删除
                  </Button>
                </Space>
              ))}
              <Form.ErrorList errors={errors} />
              <Form.Item>
                <Button type="dashed" onClick={() => add()}>
                  添加明细行
                </Button>
              </Form.Item>
            </>
          )}
        </Form.List>

        <Space>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            保存
          </Button>
          <Button onClick={() => navigate(-1)}>返回</Button>
        </Space>
      </Form>
    </Card>
  );
}
