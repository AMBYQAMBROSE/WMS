import { useState } from "react";

import { useNavigation, usePreventRemove } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen, { ContextBar } from "@/components/Screen";
import { Button, Card, Divider, IconButton, ListRow, Pill, QtyField, Stat } from "@/components/ui";
import { errorText } from "@/lib/api";
import { confirm, haptic, useNotice } from "@/lib/feedback";
import { fetchBalances, fmtQty, parseQty } from "@/lib/inbound";
import type { MobileLocation, StockBalance } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

interface Entry {
  key: number;
  balance: StockBalance;
  qty: number;
  to: MobileLocation;
}

const CONFIG = {
  putaway: {
    verb: "Putaway",
    fromLabel: "Scan source location (dock)",
    targetLabel: "Scan target bin",
    targetTypes: ["BIN"],
    targetName: "bin",
  },
  move: {
    verb: "Move",
    fromLabel: "Scan source location",
    targetLabel: "Scan target location",
    targetTypes: ["BIN", "DOCK"],
    targetName: "location",
  },
} as const;

let nextKey = 1;

/** Shared by putaway and move: scan source location -> scan item (choose batch if several) -> quantity -> scan target location -> submit */
export default function TransferScreen({ kind }: { kind: keyof typeof CONFIG }) {
  const cfg = CONFIG[kind];
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const navigation = useNavigation();
  const findItem = useMasterData((st) => st.findItem);
  const findLocation = useMasterData((st) => st.findLocation);
  const submitOp = useQueue((st) => st.submit);

  const [from, setFrom] = useState<MobileLocation | null>(null);
  const [balances, setBalances] = useState<StockBalance[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [choices, setChoices] = useState<StockBalance[]>([]);
  const [editing, setEditing] = useState<StockBalance | null>(null);
  const [qtyText, setQtyText] = useState("");
  const [notice, setNotice] = useNotice();
  const [busy, setBusy] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  usePreventRemove(entries.length > 0, ({ data }) =>
    confirm(`Discard this ${cfg.verb.toLowerCase()}?`, `${entries.length} line(s) have not been submitted.`, "Discard", () =>
      navigation.dispatch(data.action),
    ),
  );

  const used = (b: StockBalance) => entries.filter((e) => e.balance.id === b.id).reduce((sum, e) => sum + e.qty, 0);
  const available = (b: StockBalance) => b.qty_on_hand - used(b);

  /** keepNotice: keep the "done" message when stock is refreshed after a successful submit instead of overwriting it */
  const loadFrom = async (loc: MobileLocation, keepNotice = false) => {
    setBusy(true);
    try {
      const { data, cachedAt: cached } = await fetchBalances(loc.id, loc.code);
      setFrom(loc);
      setBalances(data);
      setCachedAt(cached ?? null);
      if (keepNotice && !cached) return;
      if (cached) {
        setNotice({ kind: "warning", text: `Offline: using stock cached at ${new Date(cached).toLocaleString()}; the server decides on submit` });
      } else if (!data.length) {
        setNotice({ kind: "warning", text: `Location ${loc.code} has no stock` });
      } else {
        setNotice(null);
        haptic("tick");
      }
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const scanFrom = (code: string) => {
    const loc = findLocation(code);
    if (!loc) return setNotice({ kind: "error", text: `Location ${code} not found (for new locations, update master data on the home screen first)` });
    if (loc.is_locked) return setNotice({ kind: "error", text: `Location ${loc.code} is locked` });
    void loadFrom(loc);
  };

  const startEdit = (b: StockBalance) => {
    setChoices([]);
    setEditing(b);
    setQtyText(fmtQty(available(b)));
    setNotice(null);
  };

  const scanItem = (code: string) => {
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code} (for new items, update master data on the home screen first)` });
    const rows = balances.filter((b) => b.item.id === match.item.id && available(b) > 0);
    if (!rows.length) {
      return setNotice({ kind: "error", text: `No ${match.item.sku_code} stock available at ${from?.code}` });
    }
    haptic("tick");
    const lot = match.lot;
    const sameLot = (l: { batch_no: string | null; expiry_date: string | null }) =>
      (!lot?.batchNo || l.batch_no === lot.batchNo) && (!lot?.expiryDate || l.expiry_date === lot.expiryDate);
    const matching = lot?.batchNo || lot?.expiryDate ? rows.filter(sameLot) : rows;
    if (lot && !matching.length) return setNotice({ kind: "error", text: `No ${match.item.sku_code} of batch ${lot.batchNo ?? lot.expiryDate} at ${from?.code}` });
    if (matching.length === 1) {
      startEdit(matching[0]);
      if (lot?.qty && lot.qty <= available(matching[0])) setQtyText(fmtQty(lot.qty));
      return;
    }
    // The item has several batches at this location: let the operator choose by the batch on the goods
    setChoices(matching);
    setNotice({ kind: "info", text: "This item has several batches; choose the batch on the goods" }, { silent: true });
  };

  const scanTarget = (code: string) => {
    if (!editing || !from) return;
    const qty = parseQty(qtyText);
    if (qty === null) return setNotice({ kind: "error", text: "Quantity must be a number greater than 0 (up to 4 decimals)" });
    if (qty > available(editing)) {
      return setNotice({ kind: "error", text: `Exceeds the available quantity ${fmtQty(available(editing))}` });
    }
    const to = findLocation(code);
    if (!to) return setNotice({ kind: "error", text: `Location ${code} not found` });
    if (!(cfg.targetTypes as readonly string[]).includes(to.location_type)) {
      return setNotice({ kind: "error", text: `${to.code} is not a ${cfg.targetName}; the target must be a ${cfg.targetName}` });
    }
    if (to.is_locked) return setNotice({ kind: "error", text: `Target ${cfg.targetName} ${to.code} is locked` });
    if (to.id === from.id) return setNotice({ kind: "error", text: `The target ${cfg.targetName} cannot be the source location` });
    setEntries([...entries, { key: nextKey++, balance: editing, qty, to }]);
    setEditing(null);
    setNotice({ kind: "success", text: `${editing.item.sku_code} × ${fmtQty(qty)} → ${to.code} added` }, { silent: true });
    haptic("tick");
  };

  const submit = async () => {
    if (!from || !entries.length) return;
    setBusy(true);
    const outcome = await submitOp(kind, `${cfg.verb} ${from.code}`, {
      lines: entries.map((e) => ({
        item_id: e.balance.item.id,
        uom_id: e.balance.item.base_uom.id,
        qty: e.qty,
        batch_no: e.balance.batch_no,
        expiry_date: e.balance.expiry_date,
        from_location_id: from.id,
        to_location_id: e.to.id,
      })),
    }, entries.map(
      (e) => `${e.balance.item.sku_code} × ${fmtQty(e.qty)} → ${e.to.code}${e.balance.batch_no ? ` batch ${e.balance.batch_no}` : ""}`,
    ));
    setBusy(false);
    if (outcome.status === "failed") {
      setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });
      return;
    }
    setEntries([]);
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `${cfg.verb} done, document no. ${outcome.docNo}` }
        : { kind: "warning", text: `Saved on this device; it will be submitted when back online (${outcome.reason})` },
    );
    if (outcome.status === "done") void loadFrom(from, true);
  };

  const clearFrom = () => {
    setFrom(null);
    setEntries([]);
    setEditing(null);
    setChoices([]);
    setCachedAt(null);
  };
  const changeFrom = () => {
    if (!entries.length) return clearFrom();
    confirm("Change source location?", `${entries.length} line(s) not submitted yet will be discarded.`, "Discard", clearFrom);
  };

  const step = !from ? 0 : editing ? 2 : 1;

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={["Source", "Item", "Target"]}
      step={step}
      footer={
        from ? (
          <Button
            title={`Submit ${cfg.verb.toLowerCase()} (${entries.length} lines)`}
            icon="check-circle-outline"
            onPress={() => void submit()}
            disabled={!entries.length || !!editing}
            loading={busy}
            testID={`submit-${kind}`}
          />
        ) : undefined
      }
    >
      {!from ? (
        <ScanInput label={cfg.fromLabel} icon="map-marker-radius" onScan={scanFrom} active={!busy} testID="scan-from" />
      ) : (
        <>
          <ContextBar
            items={[{ icon: "map-marker-radius", label: "Source location", value: from.code, sub: from.name }]}
            onChange={changeFrom}
            badge={
              <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
                <Pill icon="package-variant-closed" text={`${balances.length} stock line${balances.length === 1 ? "" : "s"}`} />
                {cachedAt && <Pill tone="warning" icon="cloud-off-outline" text={`Cached ${new Date(cachedAt).toLocaleTimeString()}`} />}
              </View>
            }
          />

          <ScanInput label="Scan item barcode" onScan={scanItem} active={!editing && !choices.length && !busy} testID="scan-item" />

          {choices.length > 0 && (
            <Card title="Choose the batch on the goods" icon="layers-outline">
              {choices.map((b) => (
                <ListRow
                  key={b.id}
                  title={`Batch ${b.batch_no ?? "-"}`}
                  subtitle={`Exp ${b.expiry_date ?? "-"}`}
                  right={<Text style={s.avail}>{fmtQty(available(b))}</Text>}
                  onPress={() => startEdit(b)}
                />
              ))}
              <Button title="Cancel" variant="ghost" compact onPress={() => setChoices([])} />
            </Card>
          )}

          {editing && (
            <Card style={s.panel}>
              <View style={{ flexDirection: "row", alignItems: "flex-start", gap: space.sm }}>
                <View style={{ flex: 1 }}>
                  <Text style={s.sku}>{editing.item.sku_code}</Text>
                  <Text style={s.name}>{editing.item.name}</Text>
                </View>
                {editing.batch_no && <Pill tone="info" icon="layers-outline" text={editing.batch_no} />}
              </View>
              <View style={{ flexDirection: "row" }}>
                <Stat label="Available" value={`${fmtQty(available(editing))} ${editing.item.base_uom.code}`} />
                {editing.expiry_date && <Stat label="Expiry" value={editing.expiry_date} />}
              </View>
              <QtyField label="Quantity" unit={editing.item.base_uom.code} value={qtyText} onChangeText={setQtyText} testID="qty" />
              <ScanInput label={cfg.targetLabel} icon="map-marker-radius" onScan={scanTarget} testID="scan-target" />
              <Button title="Cancel" variant="secondary" onPress={() => setEditing(null)} />
            </Card>
          )}

          {entries.length > 0 && (
            <Card title={`This ${cfg.verb.toLowerCase()} (${entries.length} lines)`} icon="playlist-check">
              {entries.map((e, i) => (
                <View key={e.key}>
                  {i > 0 && <Divider />}
                  <View style={s.entry}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.entryTitle}>
                        {e.balance.item.sku_code} × {fmtQty(e.qty)}
                      </Text>
                      <Text style={s.entrySub}>
                        {`→ ${e.to.code}`}
                        {e.balance.batch_no ? `  ·  Batch ${e.balance.batch_no}` : ""}
                      </Text>
                    </View>
                    <IconButton
                      icon="trash-can-outline"
                      tone="danger"
                      label={`Delete ${e.balance.item.sku_code}`}
                      onPress={() => setEntries(entries.filter((x) => x.key !== e.key))}
                    />
                  </View>
                </View>
              ))}
            </Card>
          )}

          {!editing && !choices.length && balances.length > 0 && (
            <Card title={`Stock at ${from.code}`} icon="package-variant-closed">
              {balances.map((b, i) => (
                <View key={b.id}>
                  {i > 0 && <Divider />}
                  <View style={s.entry}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.entryTitle} numberOfLines={1}>
                        {b.item.sku_code} <Text style={{ fontWeight: "400", color: c.textSecondary }}>{b.item.name}</Text>
                      </Text>
                      {b.batch_no && <Text style={s.entrySub}>Batch {b.batch_no}</Text>}
                    </View>
                    <Text style={[s.avail, available(b) <= 0 && { color: c.textMuted }]}>
                      {fmtQty(available(b))} {b.item.base_uom.code}
                    </Text>
                  </View>
                </View>
              ))}
            </Card>
          )}
        </>
      )}
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    panel: { borderColor: c.primary, borderWidth: 2, borderRadius: radius.lg },
    sku: { fontSize: 22, fontWeight: "800", color: c.text },
    name: { fontSize: 15, color: c.textSecondary },
    avail: { fontSize: 16, fontWeight: "700", color: c.text, fontVariant: ["tabular-nums"] },
    entry: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 6 },
    entryTitle: { fontSize: 16, fontWeight: "600", color: c.text, fontVariant: ["tabular-nums"] },
    entrySub: { fontSize: 13, color: c.textMuted },
  });
