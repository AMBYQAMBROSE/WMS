import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { Dayjs } from "dayjs";
import { useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { CountLine, CycleCount } from "@/api/types";
import { DocTitle } from "@/components/ui";
import { ActionButton, formatDateTime, preventEnterSubmit } from "@/components/documents";
import { ItemSelect, useItemRecords } from "@/components/selects";

interface EntryBody {
  location_id: string;
  item_id: string;
  qty: number;
  batch_no: string | null;
  expiry_date: string | null;
}

interface ExtraValues {
  location_id: string;
  item_id: string;
  qty: number;
  batch_no?: string;
  expiry_date?: Dayjs;
}

const variance = (l: CountLine) =>
  l.qty_planned === null || l.counted_at === null ? null : Math.round((l.qty_actual - l.qty_planned) * 10000) / 10000;

export default function CycleCountDetailPage() {
  const { id = "" } = useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, number | null>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [extraForm] = Form.useForm<ExtraValues>();
  const extraItemId = Form.useWatch("item_id", extraForm);
  const [extraItem] = useItemRecords([extraItemId]);

  const queryKey = ["cycle-counts", id];
  const { data: doc, isLoading } = useQuery({
    queryKey,
    queryFn: async () => (await apiClient.get<CycleCount>(`/cycle-counts/${id}`)).data,
  });

  const onDoc = (updated: CycleCount) => {
    queryClient.setQueryData(queryKey, updated);
    queryClient.invalidateQueries({ queryKey: ["cycle-counts", "list"] });
  };

  const record = useMutation({
    mutationFn: async (body: EntryBody) =>
      (await apiClient.post<CycleCount>(`/cycle-counts/${id}/counts`, body)).data,
    onSuccess: (updated, body) => {
      onDoc(updated);
      setDrafts((d) => {
        const next = { ...d };
        delete next[`${body.location_id}|${body.item_id}|${body.batch_no}|${body.expiry_date}`];
        return next;
      });
    },
    onError: showError,
  });

  const action = useMutation({
    mutationFn: async ({ name, body }: { name: string; body?: unknown }) =>
      (await apiClient.post<CycleCount>(`/cycle-counts/${id}/${name}`, body)).data,
    onSuccess: (updated, { name }) => {
      onDoc(updated);
      setSelected([]);
      if (name === "post") queryClient.invalidateQueries({ queryKey: ["stock"] });
      message.success(name === "recount" ? "Recount requested; the selected lines must be counted again" : "Done");
    },
    onError: showError,
  });

  if (isLoading || !doc) return <Spin />;

  const counting = doc.status === "COUNTING";
  // Only people who can enter counts see the inputs and the add-line form; read-only users see the results
  const canCount = counting && can("cycle_count.count");
  const canApprove = counting && can("cycle_count.post");
  const blind = doc.lines.every((l) => l.qty_planned === null);
  const lineKey = (l: CountLine) => `${l.to_location?.id}|${l.item.id}|${l.batch_no}|${l.expiry_date}`;
  const pending = doc.lines.filter((l) => !l.counted_at).length;
  const differing = doc.lines.filter((l) => (variance(l) ?? 0) !== 0).length;

  const saveLine = (l: CountLine) => {
    const qty = drafts[lineKey(l)];
    if (qty === null || qty === undefined) return;
    record.mutate({
      location_id: l.to_location!.id,
      item_id: l.item.id,
      qty,
      batch_no: l.batch_no,
      expiry_date: l.expiry_date,
    });
  };

  const addExtra = (v: ExtraValues) =>
    record.mutate(
      {
        location_id: v.location_id,
        item_id: v.item_id,
        qty: v.qty,
        batch_no: v.batch_no || null,
        expiry_date: v.expiry_date?.format("YYYY-MM-DD") ?? null,
      },
      { onSuccess: () => extraForm.resetFields() },
    );

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Cycle count"} no={doc.doc_no} status={doc.status} historyOf={doc.id} />}
        extra={
          counting && (
            <Space>
              {canApprove && (
                <Button
                  disabled={!selected.length}
                  loading={action.isPending}
                  onClick={() => action.mutate({ name: "recount", body: { line_ids: selected } })}
                >
                  Request recount of selected lines ({selected.length})
                </Button>
              )}
              <ActionButton
                perm="cycle_count.post"
                type="primary"
                label="Post count"
                confirm="Posting adjusts stock to the counted quantities (count gain/loss) and unfreezes the locations. Continue?"
                onConfirm={() => action.mutate({ name: "post" })}
                loading={action.isPending}
              />
              <ActionButton
                perm="cycle_count.cancel"
                danger
                label="Cancel count"
                confirm="Entered counts are discarded and the locations unfrozen. Continue?"
                onConfirm={() => action.mutate({ name: "cancel" })}
                loading={action.isPending}
              />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="Started">{formatDateTime(doc.created_at)}</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(doc.posted_at)}</Descriptions.Item>
          <Descriptions.Item label="Locations" span={3}>
            {doc.count_locations.map((cl) => (
              <Tag key={cl.location.id}>{cl.location.code}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>
        <Space size="large">
          <Statistic title="Lines" value={doc.lines.length} />
          <Statistic title="To count" value={pending} styles={{ content: pending ? { color: "#d48806" } : undefined }} />
          {!blind && <Statistic title="With difference" value={differing} styles={{ content: differing ? { color: "#cf1322" } : undefined }} />}
        </Space>
        {blind && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
            Blind count: you cannot see book quantities; enter exactly what you find.
          </Typography.Paragraph>
        )}
      </Card>

      <Card title="Count lines">
        <Table<CountLine>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={doc.lines}
          rowSelection={
            canApprove && !blind
              ? {
                  selectedRowKeys: selected,
                  onChange: (keys) => setSelected(keys as string[]),
                  getCheckboxProps: (l) => ({ disabled: !l.counted_at }),
                }
              : undefined
          }
          columns={[
            { title: "Location", render: (_, l) => l.to_location?.code },
            { title: "SKU", render: (_, l) => l.item.sku_code },
            { title: "Item", render: (_, l) => l.item.name },
            { title: "Batch", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            ...(blind ? [] : [{ title: "Book qty", dataIndex: "qty_planned" }]),
            {
              title: "Counted qty",
              render: (_, l) => {
                if (!canCount) return l.counted_at ? l.qty_actual : "";
                const key = lineKey(l);
                const draft = drafts[key];
                return (
                  <Space>
                    <InputNumber
                      min={0}
                      style={{ width: 100 }}
                      placeholder={l.counted_at ? String(l.qty_actual) : "To count"}
                      value={draft ?? undefined}
                      onChange={(v) => setDrafts((d) => ({ ...d, [key]: v }))}
                      onPressEnter={() => saveLine(l)}
                    />
                    <Button size="small" disabled={draft === null || draft === undefined} onClick={() => saveLine(l)}>
                      Save
                    </Button>
                  </Space>
                );
              },
            },
            ...(blind
              ? []
              : [
                  {
                    title: "Difference",
                    render: (_: unknown, l: CountLine) => {
                      const v = variance(l);
                      if (v === null) return "";
                      return <Typography.Text type={v === 0 ? "success" : "danger"}>{v > 0 ? `+${v}` : v}</Typography.Text>;
                    },
                  },
                ]),
            {
              title: "Status",
              render: (_, l) => {
                const last = l.count_entries[l.count_entries.length - 1];
                const history = l.count_entries
                  .map((e) => `Round ${e.round}: ${e.qty} (${e.counter.display_name} ${formatDateTime(e.counted_at)})`)
                  .join("\n");
                if (!l.counted_at) {
                  return <Tag color="orange">{l.count_entries.length ? `Recount (round ${l.count_entries.length + 1})` : "To count"}</Tag>;
                }
                return (
                  <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{history}</span>}>
                    <Tag color="green">
                      Counted, round {last.round} · {last.counter.display_name}
                    </Tag>
                  </Tooltip>
                );
              },
            },
          ]}
        />
      </Card>

      {canCount && (
        <Card title="Add: items found that are not on the books">
          <Form form={extraForm} layout="inline" onKeyDown={preventEnterSubmit} onFinish={addExtra}>
            <Form.Item name="location_id" rules={[{ required: true, message: "Choose a location" }]}>
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="Location"
                style={{ width: 160 }}
                options={doc.count_locations.map((cl) => ({ value: cl.location.id, label: cl.location.code }))}
              />
            </Form.Item>
            <Form.Item name="item_id" rules={[{ required: true, message: "Choose an item" }]}>
              <ItemSelect placeholder="Item" style={{ width: 240 }} />
            </Form.Item>
            {extraItem?.is_batch_managed && (
              <Form.Item name="batch_no" rules={[{ required: true, message: "Batch" }]}>
                <Input placeholder="Batch no." style={{ width: 120 }} />
              </Form.Item>
            )}
            {extraItem?.is_expiry_managed && (
              <Form.Item name="expiry_date" rules={[{ required: true, message: "Expiry date" }]}>
                <DatePicker placeholder="Expiry date" />
              </Form.Item>
            )}
            <Form.Item name="qty" rules={[{ required: true, message: "Quantity" }]}>
              <InputNumber min={0} placeholder="Counted qty" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={record.isPending}>
              Add
            </Button>
          </Form>
        </Card>
      )}
    </Space>
  );
}
