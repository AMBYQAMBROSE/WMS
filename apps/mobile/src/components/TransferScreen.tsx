import { useState } from "react";

import { Pressable, ScrollView, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import { Banner, Button, Card, Field, Row, colors, styles, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { fetchBalances, fmtQty, parseQty } from "@/lib/inbound";
import type { MobileLocation, StockBalance } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";

interface Entry {
  key: number;
  balance: StockBalance;
  qty: number;
  to: MobileLocation;
}

const CONFIG = {
  putaway: {
    verb: "Putaway",
    fromLabel: "① Scan source location (dock)",
    targetLabel: "③ Scan target bin",
    targetTypes: ["BIN"],
    targetName: "bin",
  },
  move: {
    verb: "Move",
    fromLabel: "① Scan source location",
    targetLabel: "③ Scan target location",
    targetTypes: ["BIN", "DOCK"],
    targetName: "location",
  },
} as const;

/** Shared by putaway and move: scan source location -> scan item (choose batch if several) -> quantity -> scan target location -> submit */
export default function TransferScreen({ kind }: { kind: keyof typeof CONFIG }) {
  const cfg = CONFIG[kind];
  const findItem = useMasterData((s) => s.findItem);
  const findLocation = useMasterData((s) => s.findLocation);
  const submitOp = useQueue((s) => s.submit);

  const [from, setFrom] = useState<MobileLocation | null>(null);
  const [balances, setBalances] = useState<StockBalance[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [choices, setChoices] = useState<StockBalance[]>([]);
  const [editing, setEditing] = useState<StockBalance | null>(null);
  const [qtyText, setQtyText] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  const used = (b: StockBalance) => entries.filter((e) => e.balance.id === b.id).reduce((s, e) => s + e.qty, 0);
  const available = (b: StockBalance) => b.qty_on_hand - used(b);

  /** keepNotice: keep the "done" message when stock is refreshed after a successful submit instead of overwriting it */
  const loadFrom = async (loc: MobileLocation, keepNotice = false) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchBalances(loc.id, loc.code);
      setFrom(loc);
      setBalances(data);
      if (keepNotice && !cachedAt) return;
      setNotice(
        cachedAt
          ? { kind: "warning", text: `Offline: using stock cached at ${new Date(cachedAt).toLocaleString()}; the server decides on submit` }
          : data.length
            ? null
            : { kind: "warning", text: `Location ${loc.code} has no stock` },
      );
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
    if (rows.length === 1) return startEdit(rows[0]);
    // The item has several batches at this location: let the operator choose by the batch on the goods
    setChoices(rows);
    setNotice({ kind: "info", text: "This item has several batches; choose the batch on the goods" });
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
    setEntries([...entries, { key: Date.now(), balance: editing, qty, to }]);
    setEditing(null);
    setNotice(null);
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
    });
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

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Banner notice={notice} />

      {!from ? (
        <ScanInput label={cfg.fromLabel} onScan={scanFrom} active={!busy} testID="scan-from" />
      ) : (
        <>
          <Card>
            <Row label="Source location" value={`${from.code} ${from.name}`} />
          </Card>

          <ScanInput
            label="② Scan item barcode"
            onScan={scanItem}
            active={!editing && !choices.length && !busy}
            testID="scan-item"
          />

          {choices.length > 0 && (
            <Card>
              {choices.map((b) => (
                <Button
                  key={b.id}
                  variant="default"
                  title={`Batch ${b.batch_no ?? "-"}  Exp ${b.expiry_date ?? "-"}  Available ${fmtQty(available(b))}`}
                  onPress={() => startEdit(b)}
                />
              ))}
            </Card>
          )}

          {editing && (
            <Card>
              <Text style={styles.title}>
                {editing.item.sku_code} {editing.item.name}
              </Text>
              {editing.batch_no && <Row label="Batch" value={editing.batch_no} />}
              <Row label="Available" value={`${fmtQty(available(editing))} ${editing.item.base_uom.code}`} />
              <Field
                label={`Quantity (${editing.item.base_uom.code})`}
                value={qtyText}
                onChangeText={setQtyText}
                keyboardType="decimal-pad"
                selectTextOnFocus
                testID="qty"
              />
              <ScanInput label={cfg.targetLabel} onScan={scanTarget} testID="scan-target" />
              <Button title="Cancel" variant="default" onPress={() => setEditing(null)} />
            </Card>
          )}

          {entries.length > 0 && (
            <Card>
              <Text style={styles.title}>
                This {cfg.verb.toLowerCase()} ({entries.length} lines)
              </Text>
              {entries.map((e) => (
                <View key={e.key} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={{ flex: 1, fontSize: 15 }}>
                    {e.balance.item.sku_code} × {fmtQty(e.qty)}
                    {e.balance.batch_no ? ` Batch ${e.balance.batch_no}` : ""} → {e.to.code}
                  </Text>
                  <Pressable onPress={() => setEntries(entries.filter((x) => x.key !== e.key))}>
                    <Text style={{ color: colors.danger, fontSize: 15 }}>Delete</Text>
                  </Pressable>
                </View>
              ))}
            </Card>
          )}

          <Button
            title={`Submit ${cfg.verb.toLowerCase()} (${entries.length} lines)`}
            onPress={submit}
            disabled={!entries.length || !!editing}
            loading={busy}
            testID={`submit-${kind}`}
          />
          <Button
            title="Change source location"
            variant="default"
            onPress={() => {
              setFrom(null);
              setEntries([]);
              setEditing(null);
              setChoices([]);
            }}
          />
        </>
      )}
    </ScrollView>
  );
}
