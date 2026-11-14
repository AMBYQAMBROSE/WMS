import { useEffect, useRef } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Form, Input, InputNumber, Table, Tooltip, message } from "antd";
import { DeleteOutlined, PlusOutlined, SplitCellsOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import { preventEnterSubmit } from "@/components/documents";
import { ItemSelect, LocationSelect, UomSelect, useItemRecords } from "@/components/selects";
import { FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

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

/** Line-by-line entry form for putaways (lines may come from a goods receipt). Moves use the location-to-location page instead. */
export default function TransferForm({
  path,
  docLabel,
  targetTypes,
  targetLabel,
  sourceGrn,
  remaining,
}: {
  path: "putaways" | "moves";
  docLabel: string;
  targetTypes: string[];
  targetLabel: string;
  sourceGrn?: Document;
  /** Per receipt line id, the quantity no putaway covers yet; lines with nothing left are not offered */
  remaining?: Record<string, number>;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const unsaved = useUnsavedChanges();

  const left = (l: Document["lines"][number]) => remaining?.[l.id] ?? l.qty_actual;
  const open = sourceGrn?.lines.filter((l) => left(l) > 0) ?? [];
  const nothingLeft = !!sourceGrn && sourceGrn.status === "POSTED" && open.length === 0;

  // Fill the form once per source document, not on every refetch (live updates, window focus): that would wipe the user's edits
  const filledFrom = useRef<string>(undefined);
  useEffect(() => {
    if (sourceGrn && filledFrom.current !== sourceGrn.id) {
      filledFrom.current = sourceGrn.id;
      form.setFieldValue(
        "lines",
        open.length
          ? open.map((l) => ({
              item_id: l.item.id,
              uom_id: l.uom.id,
              qty: left(l),
              batch_no: l.batch_no ?? undefined,
              expiry_date: l.expiry_date ? dayjs(l.expiry_date) : undefined,
              from_location_id: sourceGrn.location?.id,
            }))
          : [{}],
      );
    }
  }, [sourceGrn, form]); // filled once per receipt: `open` is read at that moment only

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
      unsaved.reset();
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
      {nothingLeft && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="Everything on this goods receipt is already on a putaway"
          description="Nothing is prefilled. To move stock that is still on the dock, enter the lines yourself."
        />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
        {...unsaved.formProps}
      >
        <FormSection title="Details">
          <Form.Item name="remark" label="Remark" style={{ maxWidth: 520 }}>
            <Input maxLength={400} placeholder="Optional" />
          </Form.Item>
        </FormSection>
        <FormSection
          title="Lines"
          description={sourceGrn ? "Prefilled from the goods receipt. Split a line to put one batch into several bins." : "One line per item, batch and location pair."}
        >
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
                        <UomSelect item={itemOf(f.name)} style={{ width: 120 }} />
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
                    title: "",
                    width: 84,
                    render: (_, f) => (
                      <span style={{ display: "inline-flex", gap: 2 }}>
                        <Tooltip title="Split into another line">
                          <Button
                            type="text"
                            size="small"
                            icon={<SplitCellsOutlined />}
                            aria-label={`Split line ${f.name + 1}`}
                            onClick={() =>
                              add({ ...form.getFieldValue(["lines", f.name]), qty: undefined, to_location_id: undefined }, f.name + 1)
                            }
                          />
                        </Tooltip>
                        <Tooltip title="Remove line">
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            aria-label={`Remove line ${f.name + 1}`}
                            onClick={() => remove(f.name)}
                            disabled={fields.length === 1}
                          />
                        </Tooltip>
                      </span>
                    ),
                  },
                ]}
              />
              {!sourceGrn && (
                <Button type="dashed" block icon={<PlusOutlined />} style={{ marginTop: 12 }} onClick={() => add({})}>
                  Add line
                </Button>
              )}
            </>
          )}
        </Form.List>
        </FormSection>
        <FormFooter note="Created as a draft; post it once the goods are moved">
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
