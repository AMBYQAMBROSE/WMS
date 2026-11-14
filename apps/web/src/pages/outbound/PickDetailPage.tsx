import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, InputNumber, Space, Table, Typography, message } from "antd";
import { Link, useParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Pick, PickLine } from "@/api/types";
import { DESC_COLUMNS, DetailSkeleton, DocTitle, ErrorState, Pill, QtyProgress, formatQty } from "@/components/ui";
import { ActionButton, formatDateTime } from "@/components/documents";

export default function PickDetailPage() {
  const { id = "" } = useParams();
  const can = useCan();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, number | null>>({});
  const queryKey = ["picks", id];

  const { data: pick, isLoading, error, refetch } = useQuery({
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
      message.success(
        name === "confirm-all" ? "All lines confirmed at the allocated quantity"
          : name === "reverse" ? "Goods returned to their bins; the order quantities are unallocated again"
            : "Done",
      );
    },
    onError: showError,
  });

  if (isLoading) return <DetailSkeleton />;
  if (!pick) return <ErrorState title="Could not load this pick list" error={error} onRetry={() => refetch()} back={{ to: "/picks", label: "Back to pick lists" }} />;
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
          pick.status === "POSTED" ? (
            <ActionButton
              perm="pick.cancel"
              label="Return goods to stock"
              confirm="Use this when the picked goods will not ship (order cancelled, wrong goods picked). They go back from staging to the bins they came from and the order quantities become unallocated again. Only possible before the goods ship. Continue?"
              onConfirm={() => action.mutate("reverse")}
              loading={action.isPending}
            />
          ) : open && (
            <Space wrap>
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
        <Descriptions column={DESC_COLUMNS}>
          <Descriptions.Item label="Sales order">
            {pick.ref_document && <Link className="wms-mono" to={`/sales-orders/${pick.ref_document.id}`}>{pick.ref_document.doc_no}</Link>}
          </Descriptions.Item>
          <Descriptions.Item label="Customer">{pick.partner?.name}</Descriptions.Item>
          <Descriptions.Item label="Staging"><span className="wms-mono">{pick.location?.code}</span></Descriptions.Item>
          <Descriptions.Item label="Progress">
            <div style={{ maxWidth: 220, width: "100%" }}>
              <QtyProgress done={pick.lines.length - pending} total={pick.lines.length} label="Lines confirmed" />
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="Posted">{formatDateTime(pick.posted_at) || <span className="wms-empty-value">Not yet</span>}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Pick lines" extra={<Typography.Text type="secondary">In bin order · {pending} of {pick.lines.length} to confirm</Typography.Text>}>
        <Table<PickLine>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={pick.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Bin", render: (_, l) => <span className="wms-mono">{l.from_location?.code}</span> },
            { title: "SKU", render: (_, l) => <span className="wms-mono">{l.item.sku_code}</span> },
            { title: "Item", render: (_, l) => l.item.name },
            { title: "Batch", dataIndex: "batch_no" },
            { title: "Expiry date", dataIndex: "expiry_date" },
            { title: "Allocated", align: "right", render: (_, l) => `${formatQty(l.qty_planned)} ${l.uom.code}` },
            {
              title: "Picked",
              render: (_, l) => {
                if (!canConfirm) return l.confirmed_at ? <span className="wms-num">{formatQty(l.qty_actual)}</span> : "";
                const draft = drafts[l.id];
                return (
                  <Space size={6}>
                    <InputNumber
                      min={0}
                      max={l.qty_planned}
                      aria-label={`Picked quantity for ${l.item.sku_code} at ${l.from_location?.code ?? ""}`}
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
                if (!l.confirmed_at) return <Pill tone="amber" dot>To pick</Pill>;
                const short = l.qty_actual < l.qty_planned;
                return (
                  <Space size={6}>
                    <Pill tone={short ? "red" : "green"} dot>
                      {short ? `Short ${formatQty(l.qty_planned - l.qty_actual)}` : "Picked"}
                    </Pill>
                    <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>{l.confirmer?.display_name}</Typography.Text>
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
