import { useEffect } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, DatePicker, Empty, Form, Input, InputNumber, Select, Space, Table, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { LocationSelect } from "@/components/selects";

interface GrnLineValues {
  po_line_id: string;
  qty: number;
  batch_no?: string;
  expiry_date?: Dayjs;
}

interface FormValues {
  location_id: string;
  remark?: string;
  lines: GrnLineValues[];
}

const remaining = (l: DocumentLine) => Math.max(l.qty_planned - l.qty_actual, 0);

export default function GrnCreatePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const poId = searchParams.get("po") ?? undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const { data: po } = useDocument("purchase-orders", poId);

  const { data: receivablePos } = useQuery({
    queryKey: ["purchase-orders", "receivable"],
    queryFn: async () => {
      const fetch = (status: string) =>
        apiClient.get<DocumentSummary[]>("/purchase-orders", { params: { status, limit: 200 } });
      const [confirmed, partial] = await Promise.all([fetch("CONFIRMED"), fetch("PARTIALLY_RECEIVED")]);
      return [...confirmed.data, ...partial.data];
    },
  });

  useEffect(() => {
    if (po) {
      form.setFieldValue(
        "lines",
        po.lines.filter((l) => remaining(l) > 0).map((l) => ({ po_line_id: l.id, qty: remaining(l) })),
      );
    }
  }, [po, form]);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const lines = values.lines
        .filter((l) => l.qty > 0)
        .map((l) => ({ ...l, expiry_date: l.expiry_date?.format("YYYY-MM-DD") ?? null }));
      if (!lines.length) throw new Error("没有需要收货的数量");
      return (await apiClient.post<Document>("/grns", { ...values, po_id: poId, lines })).data;
    },
    onSuccess: (grn) => {
      message.success(`已生成收货单 ${grn.doc_no}，确认无误后请过账`);
      queryClient.invalidateQueries({ queryKey: ["grns"] });
      navigate(`/grns/${grn.id}`);
    },
    onError: showError,
  });

  const poLine = (poLineId: string) => po?.lines.find((l) => l.id === poLineId);

  return (
    <Card title="新建收货单">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          采购单：
          <Select
            showSearch
            optionFilterProp="label"
            style={{ width: 360 }}
            placeholder="选择已确认的采购单"
            value={poId}
            onChange={(v) => setSearchParams({ po: v })}
            options={(receivablePos ?? []).map((p) => ({ value: p.id, label: `${p.doc_no} ${p.partner?.name ?? ""}` }))}
          />
        </Space>

        {!po ? (
          <Empty description="请先选择采购单" />
        ) : (
          <Form form={form} layout="vertical" onKeyDown={preventEnterSubmit} onFinish={(v) => save.mutate(v)}>
            <Space size="large" wrap>
              <Form.Item name="location_id" label="收货仓位" rules={[{ required: true }]}>
                <LocationSelect types={["DOCK", "BIN"]} style={{ width: 260 }} placeholder="一般选收货区" />
              </Form.Item>
              <Form.Item name="remark" label="备注">
                <Input style={{ width: 320 }} maxLength={400} />
              </Form.Item>
            </Space>

            <Form.List name="lines">
              {(fields, { add, remove }) => (
                <Table
                  rowKey="key"
                  size="small"
                  pagination={false}
                  dataSource={fields}
                  columns={[
                    {
                      title: "商品",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && `${l.item.sku_code} ${l.item.name}`;
                      },
                    },
                    { title: "单位", render: (_, f) => poLine(form.getFieldValue(["lines", f.name, "po_line_id"]))?.uom.code },
                    {
                      title: "未收",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && remaining(l);
                      },
                    },
                    {
                      title: "本次实收",
                      render: (_, f) => (
                        <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                          <InputNumber min={0} />
                        </Form.Item>
                      ),
                    },
                    {
                      title: "批次号",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l?.item.is_batch_managed ? (
                          <Form.Item name={[f.name, "batch_no"]} noStyle rules={[{ required: true, message: "必填" }]}>
                            <Input placeholder="必填" style={{ width: 140 }} />
                          </Form.Item>
                        ) : (
                          "-"
                        );
                      },
                    },
                    {
                      title: "到期日",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l?.item.is_expiry_managed ? (
                          <Form.Item name={[f.name, "expiry_date"]} noStyle rules={[{ required: true, message: "必填" }]}>
                            <DatePicker />
                          </Form.Item>
                        ) : (
                          "-"
                        );
                      },
                    },
                    {
                      title: "操作",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return (
                          <Space>
                            {l?.item.is_batch_managed && (
                              <Button size="small" onClick={() => add({ po_line_id: l.id, qty: 0 }, f.name + 1)}>
                                拆批次
                              </Button>
                            )}
                            <Button size="small" onClick={() => remove(f.name)}>
                              移除
                            </Button>
                          </Space>
                        );
                      },
                    },
                  ]}
                />
              )}
            </Form.List>

            <Space style={{ marginTop: 16 }}>
              <Button type="primary" htmlType="submit" loading={save.isPending}>
                生成收货单
              </Button>
              <Button onClick={() => navigate(-1)}>返回</Button>
            </Space>
          </Form>
        )}
      </Space>
    </Card>
  );
}
