import { useEffect, useRef } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Form, Input, InputNumber, Space, Table, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit } from "@/components/documents";
import { ItemSelect, LocationSelect, UomSelect, useItemRecords } from "@/components/selects";
import { FormFooter } from "@/components/ui";

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

/** Entry form shared by putaways and moves: they differ only in target location types, wording, and whether lines come from a goods receipt */
export default function TransferForm({
  path,
  docLabel,
  targetTypes,
  targetLabel,
  sourceGrn,
}: {
  path: "putaways" | "moves";
  docLabel: string;
  targetTypes: string[];
  targetLabel: string;
  sourceGrn?: Document;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();

  // Fill the form once per source document, not on every refetch (live updates, window focus): that would wipe the user's edits
  const filledFrom = useRef<string>(undefined);
  useEffect(() => {
    if (sourceGrn && filledFrom.current !== sourceGrn.id) {
      filledFrom.current = sourceGrn.id;
      form.setFieldValue(
        "lines",
        sourceGrn.lines.map((l) => ({
          item_id: l.item.id,
          uom_id: l.uom.id,
          qty: l.qty_actual,
          batch_no: l.batch_no ?? undefined,
          expiry_date: l.expiry_date ? dayjs(l.expiry_date) : undefined,
          from_location_id: sourceGrn.location?.id,
        })),
      );
    }
  }, [sourceGrn, form]);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const lines = values.lines.map((l) => ({
        ...l,
        batch_no: l.batch_no || null,
        expiry_date: l.expiry_date?.format("YYYY-MM-DD") ?? null,
      }));
      return (
        await apiClient.post<Document>(`/${path}`, { ...values, ref_document_id: sourceGrn?.id ?? null, lines })
      ).data;
    },
    onSuccess: (doc) => {
      message.success(`Created ${docLabel.toLowerCase()} ${doc.doc_no}; post it once the goods are moved`);
      queryClient.invalidateQueries({ queryKey: [path] });
      navigate(`/${path}/${doc.id}`);
    },
    onError: showError,
  });

  const watchedLines = Form.useWatch("lines", form);
  const items = useItemRecords(watchedLines?.map((l: { item_id?: string }) => l?.item_id) ?? []);
  const itemOf = (index: number) => items?.find((i) => i.id === watchedLines?.[index]?.item_id);

  return (
    <Card title={sourceGrn ? `Create ${docLabel.toLowerCase()} from goods receipt ${sourceGrn.doc_no}` : `New ${docLabel.toLowerCase()}`}>
      {sourceGrn && sourceGrn.status !== "POSTED" && (
        <Alert type="warning" style={{ marginBottom: 16 }} title="The goods receipt is not posted yet and cannot be put away" />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
      >
        <Form.Item name="remark" label="Remark">
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
                    title: "From location",
                    render: (_, f) => (
                      <Form.Item name={[f.name, "from_location_id"]} noStyle rules={[{ required: true }]}>
                        <LocationSelect types={["DOCK", "BIN"]} style={{ width: 170 }} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: targetLabel,
                    render: (_, f) => (
                      <Form.Item name={[f.name, "to_location_id"]} noStyle rules={[{ required: true, message: "Required" }]}>
                        <LocationSelect types={targetTypes} style={{ width: 170 }} placeholder={`Choose ${targetLabel.toLowerCase()}`} />
                      </Form.Item>
                    ),
                  },
                  {
                    title: "Actions",
                    render: (_, f) => (
                      <Space>
                        <Button
                          size="small"
                          onClick={() =>
                            add({ ...form.getFieldValue(["lines", f.name]), qty: undefined, to_location_id: undefined }, f.name + 1)
                          }
                        >
                          Split
                        </Button>
                        <Button size="small" onClick={() => remove(f.name)} disabled={fields.length === 1}>
                          Remove
                        </Button>
                      </Space>
                    ),
                  },
                ]}
              />
              {!sourceGrn && (
                <Button type="dashed" style={{ marginTop: 8 }} onClick={() => add({})}>
                  Add line
                </Button>
              )}
            </>
          )}
        </Form.List>
        <FormFooter>
          <Button
            type="primary"
            htmlType="submit"
            loading={save.isPending}
            disabled={!!sourceGrn && sourceGrn.status !== "POSTED"}
          >
            Create {docLabel.toLowerCase()}
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
