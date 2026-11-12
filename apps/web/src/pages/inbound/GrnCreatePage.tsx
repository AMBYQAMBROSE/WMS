import { useEffect, useRef } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DeleteOutlined, SplitCellsOutlined } from "@ant-design/icons";
import { Button, Card, Col, DatePicker, Form, Input, InputNumber, Row, Select, Table, Tooltip, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate, useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document, DocumentLine, DocumentSummary } from "@/api/types";
import { preventEnterSubmit, useDocument } from "@/components/documents";
import { LocationSelect } from "@/components/selects";
import { EmptyState, FormFooter, FormSection, formatQty, useUnsavedChanges } from "@/components/ui";

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
  const unsaved = useUnsavedChanges();

  const { data: receivablePos, isLoading: posLoading } = useQuery({
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
      unsaved.reset();
      message.success(`Created goods receipt ${grn.doc_no}; post it once checked`);
      queryClient.invalidateQueries({ queryKey: ["grns"] });
      navigate(`/grns/${grn.id}`);
    },
    onError: showError,
  });

  const poLine = (poLineId: string) => po?.lines.find((l) => l.id === poLineId);

  return (
    <Card title="New goods receipt">
      <div style={{ display: "grid", gap: 4 }}>
        <FormSection title="Purchase order" description="Receive against a confirmed or partially received order; its open quantities are filled in.">
          <label htmlFor="grn-po" className="wms-sr-only">Purchase order</label>
          <Select
            id="grn-po"
            showSearch
            optionFilterProp="label"
            style={{ width: "100%", maxWidth: 480 }}
            placeholder="Choose a confirmed purchase order"
            loading={posLoading}
            value={poId}
            onChange={(v) => setSearchParams({ po: v })}
            options={(receivablePos ?? []).map((p) => ({ value: p.id, label: `${p.doc_no} ${p.partner?.name ?? ""}` }))}
            notFoundContent={posLoading ? undefined : "No purchase orders waiting to be received"}
          />
        </FormSection>

        {!po ? (
          <EmptyState title="Choose a purchase order first" hint="Its open lines appear here, ready to receive." />
        ) : (
          <Form form={form} layout="vertical" onKeyDown={preventEnterSubmit} onFinish={(v) => save.mutate(v)} {...unsaved.formProps}>
            <FormSection title="Receipt details">
              <Row gutter={16}>
                <Col xs={24} md={10}>
                  <Form.Item name="location_id" label="Receiving location" rules={[{ required: true }]}>
                    <LocationSelect types={["DOCK", "BIN"]} style={{ width: "100%" }} placeholder="Usually the receiving dock" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={14}>
                  <Form.Item name="remark" label="Remark">
                    <Input maxLength={400} placeholder="Optional" />
                  </Form.Item>
                </Col>
              </Row>
            </FormSection>

            <FormSection title="Lines" description="Set the quantity actually received. Lines left at 0 are skipped.">
            <Form.List name="lines">
              {(fields, { add, remove }) => (
                <Table
                  rowKey="key"
                  size="small"
                  pagination={false}
                  dataSource={fields}
                  scroll={{ x: "max-content" }}
                  columns={[
                    {
                      title: "Item",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && (
                          <span>
                            <span className="wms-mono">{l.item.sku_code}</span> {l.item.name}
                          </span>
                        );
                      },
                    },
                    { title: "Unit", render: (_, f) => poLine(form.getFieldValue(["lines", f.name, "po_line_id"]))?.uom.code },
                    {
                      title: "Open",
                      align: "right",
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return l && formatQty(remaining(l));
                      },
                    },
                    {
                      title: "Received now",
                      render: (_, f) => (
                        <>
                          {/* Register po_line_id so onFinish includes it: antd only returns fields bound to a Form.Item */}
                          <Form.Item name={[f.name, "po_line_id"]} hidden noStyle>
                            <Input />
                          </Form.Item>
                          <Form.Item name={[f.name, "qty"]} noStyle rules={[{ required: true }]}>
                            <InputNumber min={0} aria-label={`Received quantity, line ${f.name + 1}`} />
                          </Form.Item>
                        </>
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
                      title: "",
                      width: 84,
                      render: (_, f) => {
                        const l = poLine(form.getFieldValue(["lines", f.name, "po_line_id"]));
                        return (
                          <span style={{ display: "inline-flex", gap: 2 }}>
                            {l?.item.is_batch_managed && (
                              <Tooltip title="Split batch: receive this line as several batches">
                                <Button type="text" size="small" icon={<SplitCellsOutlined />} aria-label={`Split batch, line ${f.name + 1}`} onClick={() => add({ po_line_id: l.id, qty: 0 }, f.name + 1)} />
                              </Tooltip>
                            )}
                            <Tooltip title="Remove line">
                              <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label={`Remove line ${f.name + 1}`} onClick={() => remove(f.name)} />
                            </Tooltip>
                          </span>
                        );
                      },
                    },
                  ]}
                />
              )}
            </Form.List>
            </FormSection>

            <FormFooter note="Created as a draft; posting adds the stock">
              <Button type="primary" htmlType="submit" loading={save.isPending}>
                Create goods receipt
              </Button>
              <Button onClick={() => navigate(-1)}>Cancel</Button>
            </FormFooter>
          </Form>
        )}
      </div>
    </Card>
  );
}
