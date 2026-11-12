import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SwapOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Form, Table } from "antd";
import { Link, useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { getErrorMessage } from "@/api/errors";
import type { Document, Location, StockBalance } from "@/api/types";
import { LocationSelect } from "@/components/selects";
import { DESC_COLUMNS, FormFooter, FormSection, Pill, emptyLocale, formatQty } from "@/components/ui";
import { LOCATION_TYPE_LABELS } from "@/constants/labels";

const MOVE_TYPES = ["BIN", "DOCK"];

/** Stock on a balance that is free to move; allocated stock stays behind for its order */
const movable = (b: StockBalance) => Math.max(b.qty_on_hand - b.qty_allocated, 0);

type Result = { type: "success" | "error"; text: string; doc?: Document };

/**
 * Location move: choose location A (its details and stock are shown), then choose location B and confirm. That creates
 * and posts one move document that takes everything movable at A to B.
 */
export default function MoveCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fromId, setFromId] = useState<string>();
  const [toId, setToId] = useState<string>();
  const [result, setResult] = useState<Result | null>(null);

  const from = useQuery({
    queryKey: ["locations", "one", fromId],
    queryFn: async () => (await apiClient.get<Location>(`/locations/${fromId}`)).data,
    enabled: !!fromId,
  });
  const stock = useQuery({
    queryKey: ["stock", "balances", { location_id: fromId }],
    queryFn: async () =>
      (await apiClient.get<StockBalance[]>("/stock/balances", { params: { location_id: fromId, limit: 500 } })).data,
    enabled: !!fromId,
  });

  const balances = stock.data ?? [];
  const lines = balances.filter((b) => movable(b) > 0);
  const allocated = balances.reduce((sum, b) => sum + b.qty_allocated, 0);

  const chooseFrom = (id?: string) => {
    setFromId(id);
    setToId(undefined);
    setResult(null);
  };

  const move = useMutation({
    mutationFn: async (id: string): Promise<Result> => {
      const a = from.data!;
      const to = (await apiClient.get<Location>(`/locations/${id}`)).data;
      if (to.is_locked) return { type: "error", text: `Location ${to.code} is locked` };
      if (to.id === a.id) return { type: "error", text: "Location B cannot be the same as location A" };

      // Re-read A's stock right before moving so the quantities are current
      const fresh = (await apiClient.get<StockBalance[]>("/stock/balances", { params: { location_id: a.id, limit: 500 } })).data;
      const toMove = fresh.filter((b) => movable(b) > 0);
      if (!toMove.length) return { type: "error", text: `Nothing left to move at ${a.code}` };

      const draft = (
        await apiClient.post<Document>("/moves", {
          remark: `Location move ${a.code} → ${to.code}`,
          ref_document_id: null,
          lines: toMove.map((b) => ({
            item_id: b.item.id,
            uom_id: b.item.base_uom.id,
            qty: movable(b),
            batch_no: b.batch_no,
            expiry_date: b.expiry_date,
            from_location_id: a.id,
            to_location_id: to.id,
          })),
        })
      ).data;
      try {
        const posted = (await apiClient.post<Document>(`/moves/${draft.id}/post`)).data;
        const left = fresh.reduce((sum, b) => sum + b.qty_allocated, 0);
        return {
          type: "success",
          text: `${a.code} → ${to.code} moved (${toMove.length} lines)${left > 0 ? `; ${formatQty(left)} allocated stayed at ${a.code}` : ""}`,
          doc: posted,
        };
      } catch (error) {
        return { type: "error", text: `Move ${draft.doc_no} was created but could not be posted: ${getErrorMessage(error)}`, doc: draft };
      }
    },
    onSuccess: (r) => {
      setResult(r);
      queryClient.invalidateQueries({ queryKey: ["moves"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      if (r.type === "success") {
        setFromId(undefined);
        setToId(undefined);
      }
    },
    onError: (error) => setResult({ type: "error", text: getErrorMessage(error) }),
  });

  const submitMove = () => {
    if (toId && from.data && lines.length && !move.isPending) move.mutate(toId);
  };

  const loc = from.data;
  const ready = !!loc && !loc.is_locked && !stock.isLoading && lines.length > 0;

  return (
    <Card title="New move">
      {result && (
        <Alert
          type={result.type}
          showIcon
          closable
          onClose={() => setResult(null)}
          style={{ marginBottom: 16 }}
          title={
            <>
              {result.text}
              {result.doc && (
                <>
                  {" · "}
                  <Link to={`/moves/${result.doc.id}`}>{result.doc.doc_no}</Link>
                </>
              )}
            </>
          }
        />
      )}
      <Form layout="vertical">
        <FormSection title="Location A" description="The location to move everything from.">
          <Form.Item label="Location A" style={{ maxWidth: 420 }}>
            <LocationSelect types={MOVE_TYPES} value={fromId} onChange={chooseFrom} allowClear placeholder="Choose location A" />
          </Form.Item>
        </FormSection>

        {fromId && (
          <>
            <FormSection title="Location details">
              {loc && (
                <Descriptions size="small" column={DESC_COLUMNS} style={{ marginBottom: 16 }}>
                  <Descriptions.Item label="Code">{loc.code}</Descriptions.Item>
                  <Descriptions.Item label="Name">{loc.name}</Descriptions.Item>
                  <Descriptions.Item label="Type">{LOCATION_TYPE_LABELS[loc.location_type] ?? loc.location_type}</Descriptions.Item>
                  <Descriptions.Item label="Path">{loc.path}</Descriptions.Item>
                  <Descriptions.Item label="Status">
                    {loc.is_locked ? <Pill tone="red">Locked</Pill> : <Pill tone="green">Open</Pill>}
                  </Descriptions.Item>
                  <Descriptions.Item label="Stock">
                    <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
                      <Pill tone="indigo">{`${lines.length} line${lines.length === 1 ? "" : "s"} to move`}</Pill>
                      {allocated > 0 && <Pill tone="amber">{`${formatQty(allocated)} allocated stays`}</Pill>}
                    </span>
                  </Descriptions.Item>
                </Descriptions>
              )}
              <Table<StockBalance>
                rowKey="id"
                size="small"
                pagination={false}
                loading={stock.isLoading}
                dataSource={balances}
                scroll={{ x: true }}
                locale={emptyLocale(`No stock at ${loc?.code ?? "this location"}`)}
                columns={[
                  { title: "Item", render: (_, b) => b.item.sku_code },
                  { title: "Name", render: (_, b) => b.item.name, ellipsis: true },
                  { title: "Batch no.", dataIndex: "batch_no", render: (v) => v ?? "-" },
                  { title: "Expiry date", dataIndex: "expiry_date", render: (v) => v ?? "-" },
                  { title: "On hand", align: "right", render: (_, b) => formatQty(b.qty_on_hand) },
                  { title: "Allocated", align: "right", render: (_, b) => formatQty(b.qty_allocated) },
                  { title: "To move", align: "right", render: (_, b) => <b>{formatQty(movable(b))}</b> },
                  { title: "Unit", render: (_, b) => b.item.base_uom.code },
                ]}
              />
            </FormSection>

            <FormSection title="Location B" description="Choose the target location; everything movable at location A is moved there and posted at once.">
              {loc?.is_locked && <Alert type="error" style={{ marginBottom: 12 }} title={`Location ${loc.code} is locked and cannot be moved`} />}
              {!stock.isLoading && loc && !lines.length && (
                <Alert
                  type="warning"
                  style={{ marginBottom: 12 }}
                  title={balances.length ? `All stock at ${loc.code} is allocated to orders; nothing to move` : `Location ${loc.code} has no stock`}
                />
              )}
              <Form.Item label="Location B" style={{ maxWidth: 420 }}>
                <LocationSelect
                  types={MOVE_TYPES}
                  value={toId}
                  onChange={(id?: string) => setToId(id)}
                  allowClear
                  placeholder="Choose location B"
                  disabled={!ready || move.isPending}
                />
              </Form.Item>
              <Button
                type="primary"
                icon={<SwapOutlined />}
                onClick={submitMove}
                loading={move.isPending}
                disabled={!ready || !toId || toId === fromId}
              >
                {`Move ${lines.length} line${lines.length === 1 ? "" : "s"} to location B`}
              </Button>
              {toId && toId === fromId && (
                <Alert type="error" style={{ marginTop: 12 }} title="Location B cannot be the same as location A" />
              )}
            </FormSection>
          </>
        )}

        <FormFooter>
          <Button onClick={() => navigate("/moves")}>Back to moves</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
