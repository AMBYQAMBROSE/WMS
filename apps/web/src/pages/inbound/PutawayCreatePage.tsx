import { useEffect } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Form, Input, InputNumber, Space, Table, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { ItemSelect, LocationSelect, UomSelect, useItems } from "@/components/selects";

interface LineValues {
  item_id?: string;
  uom_id?: string;
  qty?: number;
  batch_no?: string;
  expiry_date?: Dayjs;
  from_location_id?: string;
  to_location_id?: string;
}

interface FormValues {
  remark?: string;
  lines: LineValues[];
}

export default function PutawayCreatePage() {
  const [searchParams] = useSearchParams();
  const grnId = searchParams.get("grn") ?? undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const { data: items } = useItems();
  const { data: grn } = useDocument("grns", grnId);

  useEffect(() => {
    if (grn) {
      form.setFieldValue(
        "lines",
        grn.lines.map((l) => ({
          item_id: l.item.id,
          uom_id: l.uom.id,
          qty: l.qty_actual,
          batch_no: l.batch_no ?? undefined,
          expiry_date: l.expiry_date ? dayjs(l.expiry_date) : undefined,
          from_location_id: grn.location?.id,
        })),
      );
    }
  }, [grn, form]);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const lines = values.lines.map((l) => ({
        ...l,
        batch_no: l.batch_no || null,
        expiry_date: l.expiry_date?.format("YYYY-MM-DD") ?? null,
      }));
      return (await apiClient.post<Document>("/putaways", { ...values, ref_document_id: grnId ?? null, lines })).data;
    },
    onSuccess: (pa) => {
      message.success(`已生成上架单 ${pa.doc_no}，实际上架完成后请过账`);
      queryClient.invalidateQueries({ queryKey: ["putaways"] });
      navigate(`/putaways/${pa.id}`);
    },
    onError: showError,
  });

  const watchedLines = Form.useWatch("lines", form);
  const itemOf = (index: number) => items?.find((i) => i.id === watchedLines?.[index]?.item_id);

  return (
    <Card title={grn ? `按收货单 ${grn.doc_no} 上架` : "新建上架单"}>
      {grn && grn.status !== "POSTED" && (
        <Alert type="warning" style={{ marginBottom: 16 }} message="收货单尚未过账，不能上架" />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
      >
        <Form.Item name="remark" label="备注">
          <Input style={{ width: 320 }} maxLength={400} />
        </Form.Item>
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
                    title: "商品",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "item_id"]} noStyle rules={[{ required: true }]}>
                        <ItemSelect
                          style={{ width: 220 }}
                          onChange={(itemId) => {
                            const item = items?.find((i) => i.id === itemId);
                            if (item) form.setFieldValue(["lines", f.name, "uom_id"], item.base_uom_id);
                          }}
                        />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "单位",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "uom_id"]} noStyle rules={[{ required: true }]}>
                        <UomSelect style={{ width: 100 }} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "数量",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                        <InputNumber min={0.0001} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "批次号",
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
                    title: "到期日",
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
                    title: "来源仓位",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "from_location_id"]} noStyle rules={[{ required: true }]}>
                        <LocationSelect types={["DOCK", "BIN"]} style={{ width: 170 }} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "目标储位",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "to_location_id"]} noStyle rules={[{ required: true, message: "请选择" }]}>
                        <LocationSelect types={["BIN"]} style={{ width: 170 }} placeholder="选择储位" />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "操作",
                    render: (_, f) => (
                      <Space>
                        <Button
                          size="small"
                          onClick={() =>
                            add({ ...form.getFieldValue(["lines", f.name]), qty: undefined, to_location_id: undefined }, f.name + 1)
                          }
                        >
                          拆分
                        </Button>
                        <Button size="small" onClick={() => remove(f.name)} disabled={fields.length === 1}>
                          移除
                        </Button>
                      </Space>
                    ),
                  },
                ]}
              />
              {!grn && (
                <Button type="dashed" style={{ marginTop: 8 }} onClick={() => add({})}>
                  添加明细行
                </Button>
              )}
            </>
          )}
        </Form.List>
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" htmlType="submit" loading={save.isPending} disabled={!!grn && grn.status !== "POSTED"}>
            生成上架单
          </Button>
          <Button onClick={() => navigate(-1)}>返回</Button>
        </Space>
      </Form>
    </Card>
  );
}
