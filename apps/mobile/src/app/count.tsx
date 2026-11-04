import { useEffect, useState } from "react";

import { ScrollView, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import { Banner, Button, Card, Field, Row, colors, styles, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { fetchActiveCounts, fetchCount, fmtQty, parseDate } from "@/lib/inbound";
import type { CountLine, CycleCount, DocumentSummary, MobileItem, MobileLocation } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";

interface Editing {
  item: MobileItem;
  batchNo: string;
  expiryDate: string;
  /** Whether batch/expiry came from a book line (if so they cannot be edited, to avoid recording the wrong dimension) */
  fixed: boolean;
}

const keyOf = (locationId: string, itemId: string, batch: string | null, expiry: string | null) =>
  `${locationId}|${itemId}|${batch ?? ""}|${expiry ?? ""}`;

export default function CountScreen() {
  const findItem = useMasterData((s) => s.findItem);
  const findLocation = useMasterData((s) => s.findLocation);
  const submitOp = useQueue((s) => s.submit);

  const [counts, setCounts] = useState<DocumentSummary[] | null>(null);
  const [count, setCount] = useState<CycleCount | null>(null);
  const [location, setLocation] = useState<MobileLocation | null>(null);
  const [choices, setChoices] = useState<CountLine[]>([]);
  const [choiceItem, setChoiceItem] = useState<MobileItem | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [qtyText, setQtyText] = useState("");
  // Show entries that were submitted but are still in the local queue
  const [queued, setQueued] = useState<Record<string, number>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  const loadList = async () => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchActiveCounts();
      setCounts(data);
      if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached cycle count list" });
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadList();
  }, []);

  const openCount = async (summary: DocumentSummary, keepNotice = false) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchCount(summary.id, summary.doc_no);
      setCount(data);
      if (cachedAt) setNotice({ kind: "warning", text: "Offline: using the cached cycle count; entries are saved on this device and submitted when back online" });
      else if (!keepNotice) setNotice(null);
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const scanLocation = (code: string) => {
    if (!count) return;
    const loc = findLocation(code);
    const inCount = loc && count.count_locations.some((cl) => cl.location.id === loc.id);
    if (!loc || !inCount) return setNotice({ kind: "error", text: `Location ${code} is not part of cycle count ${count.doc_no}` });
    setNotice(null);
    setLocation(loc);
  };

  const linesHere = count && location ? count.lines.filter((l) => l.to_location?.id === location.id) : [];

  const startEdit = (item: MobileItem, line: CountLine | null) => {
    setChoices([]);
    setChoiceItem(null);
    setEditing({ item, batchNo: line?.batch_no ?? "", expiryDate: line?.expiry_date ?? "", fixed: !!line });
    setQtyText("");
    setNotice(null);
  };

  const scanItem = (code: string) => {
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code} (for new items, update master data on the home screen first)` });
    const item = match.item;
    const candidates = linesHere.filter((l) => l.item.id === item.id);
    const tracked = item.is_batch_managed || item.is_expiry_managed;
    if (!tracked) return startEdit(item, candidates[0] ?? null);
    if (candidates.length === 0) return startEdit(item, null);
    if (candidates.length === 1) return startEdit(item, candidates[0]);
    setChoiceItem(item);
    setChoices(candidates);
    setNotice({ kind: "info", text: "This item has several batches at this location; choose the batch on the goods" });
  };

  const submitEntry = async () => {
    if (!count || !location || !editing) return;
    const qty = Number(qtyText.trim());
    if (qtyText.trim() === "" || !Number.isFinite(qty) || qty < 0) {
      return setNotice({ kind: "error", text: "Enter the counted quantity (0 if none)" });
    }
    const batchNo = editing.batchNo.trim() || null;
    if (editing.item.is_batch_managed && !batchNo) return setNotice({ kind: "error", text: "Enter the batch no." });
    let expiryDate: string | null = null;
    if (editing.item.is_expiry_managed) {
      expiryDate = parseDate(editing.expiryDate);
      if (!expiryDate) return setNotice({ kind: "error", text: "Expiry date must be YYYY-MM-DD" });
    }

    setBusy(true);
    const entry = { location_id: location.id, item_id: editing.item.id, qty, batch_no: batchNo, expiry_date: expiryDate };
    const outcome = await submitOp("count", `Count ${count.doc_no} ${location.code} ${editing.item.sku_code}`, {
      count_id: count.id,
      entry,
    });
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });

    const label = `${editing.item.sku_code} = ${fmtQty(qty)}`;
    setEditing(null);
    if (outcome.status === "done") {
      setNotice({ kind: "success", text: `Recorded ${label}` });
      void openCount(count, true);
    } else {
      setQueued((q) => ({ ...q, [keyOf(location.id, entry.item_id, batchNo, expiryDate)]: qty }));
      setNotice({ kind: "warning", text: `${label} saved on this device; it will be submitted when back online (${outcome.reason})` });
    }
  };

  const lineStatus = (l: CountLine) => {
    const pending = queued[keyOf(l.to_location!.id, l.item.id, l.batch_no, l.expiry_date)];
    if (pending !== undefined) return { text: `Pending sync ${fmtQty(pending)}`, color: colors.warning };
    if (l.counted_at) return { text: `Counted ${fmtQty(l.qty_actual)}`, color: colors.success };
    return { text: "To count", color: colors.subtle };
  };

  if (!count) {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <Banner notice={notice} />
        <Text style={styles.title}>Choose a cycle count</Text>
        {counts?.length === 0 && <Text style={styles.hint}>No cycle counts in progress (start one in the web console)</Text>}
        {counts?.map((c) => (
          <Button
            key={c.id}
            variant="default"
            title={`${c.doc_no}${c.remark ? ` · ${c.remark}` : ""}`}
            onPress={() => void openCount(c)}
            testID={`count-${c.doc_no}`}
          />
        ))}
        <Button title="Refresh" variant="default" onPress={() => void loadList()} loading={busy} />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Banner notice={notice} />
      <Card>
        <Row label="Cycle count" value={count.doc_no} />
        <Row label="Scope" value={count.count_locations.map((cl) => cl.location.code).join(", ")} />
        {location && <Row label="Location" value={`${location.code} ${location.name}`} />}
      </Card>

      {!location ? (
        <ScanInput label="① Scan the location to count" onScan={scanLocation} active={!busy} testID="scan-count-location" />
      ) : (
        <>
          <ScanInput
            label="② Scan item barcode"
            onScan={scanItem}
            active={!editing && !choices.length && !busy}
            testID="scan-item"
          />

          {choices.length > 0 && choiceItem && (
            <Card>
              {choices.map((l) => (
                <Button
                  key={l.id}
                  variant="default"
                  title={`Batch ${l.batch_no ?? "-"}  Exp ${l.expiry_date ?? "-"}`}
                  onPress={() => startEdit(choiceItem, l)}
                />
              ))}
              <Button title="Other batch (not on book)" variant="default" onPress={() => startEdit(choiceItem, null)} />
            </Card>
          )}

          {editing && (
            <Card>
              <Text style={styles.title}>
                {editing.item.sku_code} {editing.item.name}
              </Text>
              {editing.item.is_batch_managed &&
                (editing.fixed ? (
                  <Row label="Batch" value={editing.batchNo} />
                ) : (
                  <Field
                    label="Batch no. (scannable)"
                    value={editing.batchNo}
                    onChangeText={(v) => setEditing({ ...editing, batchNo: v })}
                    testID="batch"
                  />
                ))}
              {editing.item.is_expiry_managed &&
                (editing.fixed ? (
                  <Row label="Expiry" value={editing.expiryDate} />
                ) : (
                  <Field
                    label="Expiry date YYYY-MM-DD"
                    value={editing.expiryDate}
                    onChangeText={(v) => setEditing({ ...editing, expiryDate: v })}
                    testID="expiry"
                  />
                ))}
              <Field
                label="Counted quantity (base unit, 0 if none)"
                value={qtyText}
                onChangeText={setQtyText}
                keyboardType="decimal-pad"
                autoFocus={editing.fixed || !(editing.item.is_batch_managed || editing.item.is_expiry_managed)}
                onSubmitEditing={() => void submitEntry()}
                testID="qty"
              />
              <View style={{ flexDirection: "row", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Button title="OK" onPress={() => void submitEntry()} loading={busy} testID="confirm-count" />
                </View>
                <View style={{ flex: 1 }}>
                  <Button title="Cancel" variant="default" onPress={() => setEditing(null)} />
                </View>
              </View>
            </Card>
          )}

          <Card>
            <Text style={styles.title}>Lines at this location ({linesHere.length})</Text>
            {linesHere.length === 0 && <Text style={styles.hint}>No stock on book; record whatever goods you find</Text>}
            {linesHere.map((l) => {
              const status = lineStatus(l);
              return (
                <View key={l.id} style={{ flexDirection: "row", gap: 8 }}>
                  <Text style={{ flex: 1, fontSize: 15 }}>
                    {l.item.sku_code} {l.batch_no ? `Batch ${l.batch_no}` : ""}
                    {l.qty_planned !== null ? `  Book ${fmtQty(l.qty_planned)}` : ""}
                  </Text>
                  <Text style={{ fontSize: 15, color: status.color }}>{status.text}</Text>
                </View>
              );
            })}
          </Card>

          <Button title="Change location" variant="default" onPress={() => { setLocation(null); setEditing(null); setChoices([]); }} />
        </>
      )}
      <Button
        title="Change cycle count"
        variant="default"
        onPress={() => {
          setCount(null);
          setLocation(null);
          setEditing(null);
          setQueued({});
        }}
      />
    </ScrollView>
  );
}
