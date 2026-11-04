import { useEffect, useRef } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, DatePicker, Empty, Form, Input, InputNumber, Select, Space, Table, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { LocationSelect } from "@/components/selects";
import { FormFooter } from "@/components/ui";

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

  // Fill the form once per source document, not on every refetch (live updates, window focus): that would wipe the user's edits
  const filledFrom = useRef<string>(undefined);
  useEffect(() => {
    if (po && filledFrom.current !== po.id) {
      filledFrom.current = po.id;
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
      if (!lines.length) throw new Error("Nothing to receive");
      return (await apiClient.post<Document>("/grns", { ...values, po_id: poId, lines })).data;
    },
    onSuccess: (grn) => {
      message.success(`Created goods receipt ${grn.doc_no}; post it once checked`);
      queryClient.invalidateQueries({ queryKey: ["grns"] });
      navigate(`/grns/${grn.id}`);
    },
    onError: showError,
  });

  const poLine = (poLineId: string) => po?.lines.find((l) => l.id === poLineId);

  return (
    <Card title="New goods receipt">
      <Space orientation="vertical" style={{ width: "100%" }}>
        <Space>
          Purchase order:
          <Select
            showSearch
            optionFilterProp="label"
            style={{ width: 360 }}
            placeholder="Choose a confirmed purchase order"
            value={poId}
            onChange={(v) => setSearchParams({ po: v })}
            options={(receivablePos ?? []).map((p) => ({ value: p.id, label: `${p.doc_no} ${p.partner?.name ?? ""}` }))}
          />
        </Space>

        {!po ? (
          <Empty description="Choose a purchase order first" />
        ) : (
          <Form form={form} layout="vertical" onKeyDown={preventEnterSubmit} onFinish={(v) => save.mutate(v)}>
            <Space size="large" wrap>
              <Form.Item name="location_id" label="Receiving location" rules={[{ required: true }]}>
                <LocationSelect types={["DOCK", "BIN"]} style={{ width: 260 }} placeholder="Usually the receiving dock" />
              </Form.Item>
              <Form.Item name="remark" label="Remark">
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
                      title: "Item",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && `${l.item.sku_code} ${l.item.name}`;
                      },
                    },
                    { title: "Unit", render: (_, f) => poLine(form.getFieldValue(["lines", f.name, "po_line_id"]))?.uom.code },
                    {
                      title: "Open",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && remaining(l);
                      },
                    },
                    {
                      title: "Received now",
                      render: (_, f) => (
                        <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                          <InputNumber min={0} />
                        </Form.Item>
                      ),
                    },
                    {
                      title: "Batch no.",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l?.item.is_batch_managed ? (
                          <Form.Item name={[f.name, "batch_no"]} noStyle rules={[{ required: true, message: "Required" }]}>
                            <Input placeholder="Required" style={{ width: 140 }} />
                          </Form.Item>
                        ) : (
                          "-"
                        );
                      },
                    },
                    {
                      title: "Expiry date",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l?.item.is_expiry_managed ? (
                          <Form.Item name={[f.name, "expiry_date"]} noStyle rules={[{ required: true, message: "Required" }]}>
                            <DatePicker />
                          </Form.Item>
                        ) : (
                          "-"
                        );
                      },
                    },
                    {
                      title: "Actions",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return (
                          <Space>
                            {l?.item.is_batch_managed && (
                              <Button size="small" onClick={() => add({ po_line_id: l.id, qty: 0 }, f.name + 1)}>
                                Split batch
                              </Button>
                            )}
                            <Button size="small" onClick={() => remove(f.name)}>
                              Remove
                            </Button>
                          </Space>
                        );
                      },
                    },
                  ]}
                />
              )}
            </Form.List>

            <FormFooter>
              <Button type="primary" htmlType="submit" loading={save.isPending}>
                Create goods receipt
              </Button>
              <Button onClick={() => navigate(-1)}>Cancel</Button>
            </FormFooter>
          </Form>
        )}
      </Space>
    </Card>
  );
}
