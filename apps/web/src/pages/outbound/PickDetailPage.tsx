import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, InputNumber, Space, Spin, Table, Tag, Typography, message } from "antd";
import { Link, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Pick, PickLine } from "@/api/types";
import { DocTitle } from "@/components/ui";
import { ActionButton, formatDateTime } from "@/components/documents";

export default function PickDetailPage() {
  const { id = "" } = useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, number | null>>({});
  const queryKey = ["picks", id];

  const { data: pick, isLoading } = useQuery({
    queryKey,
    queryFn: async () => (await apiClient.get<Pick>(`/picks/${id}`)).data,
  });

  const onPick = (updated: Pick) => {
    queryClient.setQueryData(queryKey, updated);
    queryClient.invalidateQueries({ queryKey: ["picks", "list"] });
    queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
  };

  const confirm = useMutation({
    mutationFn: async ({ line, qty }: { line: PickLine; qty: number }) =>
      (await apiClient.post<Pick>(`/picks/${id}/lines/${line.id}/confirm`, { qty })).data,
    onSuccess: (updated, { line }) => {
      onPick(updated);
      setDrafts((d) => {
        const next = { ...d };
        delete next[line.id];
        return next;
      });
    },
    onError: showError,
  });

  const action = useMutation({
    mutationFn: async (name: string) => (await apiClient.post<Pick>(`/picks/${id}/${name}`)).data,
    onSuccess: (updated, name) => {
      onPick(updated);
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      message.success(name === "confirm-all" ? "All lines confirmed at the allocated quantity" : "Done");
    },
    onError: showError,
  });

  if (isLoading || !pick) return <Spin />;
  const open = pick.status === "OPEN";
  const canConfirm = open && can("pick.confirm");
  const pending = pick.lines.filter((l) => !l.confirmed_at).length;

  const save = (line: PickLine) => {
    const qty = drafts[line.id];
    if (qty === null || qty === undefined) return;
    confirm.mutate({ line, qty });
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Card
        title={<DocTitle label={"Pick list"} no={pick.doc_no} status={pick.status} historyOf={pick.id} />}
        extra={
          open && (
            <Space>
              {canConfirm && pending > 0 && (
                <Button loading={action.isPending} onClick={() => action.mutate("confirm-all")}>
                  Confirm all unconfirmed lines at the allocated quantity ({pending})
                </Button>
              )}
              <ActionButton
                perm="pick.post"
                type="primary"
                label="Post pick list"
                confirm="Are all goods in staging? Posting moves the stock from the bins to staging and releases the reservation of short-picked quantities."
                onConfirm={() => action.mutate("post")}
                loading={action.isPending}
              />
              <ActionButton
                perm="pick.cancel"
                danger
                label="Cancel pick list"
                confirm="Cancelling releases every reservation and the order quantities become unallocated again. Continue?"
                onConfirm={() => action.mutate("cancel")}
                loading={action.isPending}
              />
            </Space>
          )
        }
      >
        <Descriptions column={3}>
          <Descriptions.Item label="Sales order">
            {pick.ref_document && <Link to={`/sales-orders/${pick.ref_document.id}`}>{pick.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="Customer">{pick.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Staging">{pick.location?.code}</Descriptions.Item>
          <Descriptions.Item label="To confirm">{pending} lines</Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(pick.posted_at)}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Pick lines (in bin order)">
        <Table<PickLine>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={pick.lines}
          columns={[
            { title: "Bin", render: (_, l) => l.from_location?.code },
            { title: "SKU", render: (_, l) => l.item.sku_code },
            { title: "Item", render: (_, l) => l.item.name },
            { title: "Batch", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            { title: "Allocated", render: (_, l) => `${l.qty_planned} ${l.uom.code}` },
            {
              title: "Picked",
              render: (_, l) => {
                if (!canConfirm) return l.confirmed_at ? l.qty_actual : "";
                const draft = drafts[l.id];
                return (
                  <Space>
                    <InputNumber
                      min={0}
                      max={l.qty_planned}
                      style={{ width: 100 }}
                      placeholder={l.confirmed_at ? String(l.qty_actual) : String(l.qty_planned)}
                      value={draft ?? undefined}
                      onChange={(v) => setDrafts((d) => ({ ...d, [l.id]: v }))}
                      onPressEnter={() => save(l)}
                    />
                    <Button size="small" disabled={draft === null || draft === undefined} onClick={() => save(l)}>
                      Confirm
                    </Button>
                  </Space>
                );
              },
            },
            {
              title: "Status",
              render: (_, l) => {
                if (!l.confirmed_at) return <Tag color="orange">To pick</Tag>;
                const short = l.qty_actual < l.qty_planned;
                return (
                  <Space>
                    <Tag color={short ? "red" : "green"}>{short ? `Short ${l.qty_planned - l.qty_actual}` : "Picked"}</Tag>
                    <Typography.Text type="secondary">{l.confirmer?.display_name}</Typography.Text>
                  </Space>
                );
              },
            },
          ]}
        />
      </Card>
    </Space>
  );
}
