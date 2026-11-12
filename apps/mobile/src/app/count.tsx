import { useEffect, useState } from "react";

import { useLocalSearchParams } from "expo-router";
import { RefreshControl, StyleSheet, Text, View } from "react-native";

import PhotoCapture from "@/components/PhotoCapture";
import { DateField } from "@/components/DateField";
import ScanInput from "@/components/ScanInput";
import Screen, { ContextBar } from "@/components/Screen";
import { Button, Card, Divider, EachScanToggle, EmptyState, Field, ListRow, Pill, QtyField, Row } from "@/components/ui";
import { errorText } from "@/lib/api";
import { confirm, haptic, useNotice } from "@/lib/feedback";
import { fetchActiveCounts, fetchCount, fmtQty, parseDate } from "@/lib/inbound";
import type { CountLine, CycleCount, DocumentSummary, MobileItem, MobileLocation } from "@/lib/types";
import { useMasterData, type ItemMatch } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSettings } from "@/stores/settings";
import { useTasks } from "@/stores/tasks";
import { radius, space, useStyles, useTheme, type Palette, type Tone } from "@/theme";

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
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const findItem = useMasterData((st) => st.findItem);
  const findLocation = useMasterData((st) => st.findLocation);
  const submitOp = useQueue((st) => st.submit);
  const eachScan = useSettings((st) => st.eachScanCountsOne);

  const params = useLocalSearchParams<{ doc?: string }>();
  const [counts, setCounts] = useState<DocumentSummary[] | null>(null);
  const [count, setCount] = useState<CycleCount | null>(null);
  const [location, setLocation] = useState<MobileLocation | null>(null);
  const [choices, setChoices] = useState<CountLine[]>([]);
  const [choiceItem, setChoiceItem] = useState<MobileItem | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [qtyText, setQtyText] = useState("");
  // Show entries that were submitted but are still in the local queue
  const [queued, setQueued] = useState<Record<string, number>>({});
  const [notice, setNotice] = useNotice();
  // Starts busy: the list loads on mount
  const [busy, setBusy] = useState(true);

  const applyList = ({ data, cachedAt }: Awaited<ReturnType<typeof fetchActiveCounts>>) => {
    setCounts(data);
    if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached cycle count list" }, { silent: true });
  };
  const failList = (error: unknown) => setNotice({ kind: "error", text: errorText(error) });

  const loadList = async () => {
    setBusy(true);
    try {
      applyList(await fetchActiveCounts());
    } catch (error) {
      failList(error);
    } finally {
      setBusy(false);
    }
  };

  const openCount = async (summary: DocumentSummary, keepNotice = false) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchCount(summary.id, summary.doc_no);
      setCount(data);
      if (cachedAt) {
        setNotice({ kind: "warning", text: "Offline: using the cached cycle count; entries are saved on this device and submitted when back online" });
      } else if (!keepNotice) setNotice(null);
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  // On mount, state is set from the promise callbacks rather than synchronously in the effect
  useEffect(() => {
    useTasks.getState().seen("count");
    fetchActiveCounts()
.then((result) => {
        applyList(result);
        // Opened from the home screen's scan field with this document's number
        const wanted = params.doc && result.data.find((d) => d.doc_no.toUpperCase() === params.doc!.toUpperCase());
        if (wanted) void openCount(wanted);
      }, failList)
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, []);

  const scanLocation = (code: string) => {
    if (!count) return;
    const loc = findLocation(code);
    const inCount = loc && count.count_locations.some((cl) => cl.location.id === loc.id);
    if (!loc || !inCount) return setNotice({ kind: "error", text: `Location ${code} is not part of cycle count ${count.doc_no}` });
    setNotice(null);
    haptic("tick");
    setLocation(loc);
  };

  const linesHere = count && location ? count.lines.filter((l) => l.to_location?.id === location.id) : [];

  const startEdit = (item: MobileItem, line: CountLine | null, lot?: ItemMatch["lot"]) => {
    setChoices([]);
    setChoiceItem(null);
    setEditing({
      item,
      batchNo: line?.batch_no ?? lot?.batchNo ?? "",
      expiryDate: line?.expiry_date ?? lot?.expiryDate ?? "",
      fixed: !!line,
    });
    setQtyText(lot?.qty ? fmtQty(lot.qty) : eachScan ? "1" : "");
    setNotice(null);
  };

  const scanCounting =
    eachScan && !!editing && (editing.fixed || !(editing.item.is_batch_managed || editing.item.is_expiry_managed));

  const scanItem = (code: string) => {
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code} (for new items, update master data on the home screen first)` });
    const item = match.item;
    if (editing) {
      // Continuous scanning with the panel open: every scan of the same item is one more piece
      if (item.id !== editing.item.id) {
        return setNotice({ kind: "error", text: `Finish counting ${editing.item.sku_code} first: press OK, then scan the next item` });
      }
      // A carton's own code counts its whole quantity
      const counted = (Number(qtyText.trim()) || 0) + (match.lot?.qty ?? 1);
      setQtyText(String(counted));
      setNotice({ kind: "info", text: `${item.sku_code}: ${counted}` }, { silent: true });
      haptic("tick");
      return;
    }
    haptic("tick");
    const candidates = linesHere.filter((l) => l.item.id === item.id);
    const tracked = item.is_batch_managed || item.is_expiry_managed;
    const lot = match.lot;
    if (lot && tracked && (lot.batchNo || lot.expiryDate)) {
      // The code says which batch this is: its line, or a new one with that batch filled in
      const sameLot = (l: { batch_no: string | null; expiry_date: string | null }) =>
      (!lot?.batchNo || l.batch_no === lot.batchNo) && (!lot?.expiryDate || l.expiry_date === lot.expiryDate);
      return startEdit(item, candidates.find(sameLot) ?? null, lot);
    }
    if (!tracked) return startEdit(item, candidates[0] ?? null, lot);
    if (candidates.length === 0) return startEdit(item, null);
    if (candidates.length === 1) return startEdit(item, candidates[0]);
    setChoiceItem(item);
    setChoices(candidates);
    setNotice({ kind: "info", text: "This item has several batches at this location; choose the batch on the goods" }, { silent: true });
  };

  const submitEntry = async () => {
    if (!count || !location || !editing || busy) return;
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
    }, [`${editing.item.sku_code} counted ${fmtQty(qty)} at ${location.code}${batchNo ? ` batch ${batchNo}` : ""}`]);
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

  const lineStatus = (l: CountLine): { text: string; tone: Tone } => {
    const pending = queued[keyOf(l.to_location!.id, l.item.id, l.batch_no, l.expiry_date)];
    if (pending !== undefined) return { text: `Pending sync ${fmtQty(pending)}`, tone: "warning" };
    if (l.counted_at) return { text: `Counted ${fmtQty(l.qty_actual)}`, tone: "success" };
    return { text: "To count", tone: "neutral" };
  };

  const leaveLocation = () => {
    const go = () => {
      setLocation(null);
      setEditing(null);
      setChoices([]);
    };
    if (!editing) return go();
    confirm("Change location?", `The count for ${editing.item.sku_code} has not been recorded yet.`, "Discard", go);
  };

  const leaveCount = () => {
    const go = () => {
      setCount(null);
      setLocation(null);
      setEditing(null);
      setQueued({});
    };
    if (!editing) return go();
    confirm("Change cycle count?", `The count for ${editing.item.sku_code} has not been recorded yet.`, "Discard", go);
  };

  if (!count) {
    return (
      <Screen
        notice={notice}
        onDismiss={() => setNotice(null)}
        refreshControl={<RefreshControl refreshing={busy && counts !== null} onRefresh={() => void loadList()} colors={[c.primary]} tintColor={c.primary} />}
        footer={<Button title="Refresh" variant="secondary" icon="refresh" onPress={() => void loadList()} loading={busy} />}
      >
        {counts === null ? (
          <EmptyState icon="clipboard-text-outline" title="Loading cycle counts…" />
        ) : counts.length === 0 ? (
          <EmptyState
            icon="clipboard-check-outline"
            title="No cycle counts in progress"
            text="Start a cycle count in the web console; it appears here. Pull down to check again."
          />
        ) : (
          <>
            <Text style={s.listHeader}>Choose a cycle count</Text>
            {counts.map((cc) => (
              <ListRow
                key={cc.id}
                icon="clipboard-list-outline"
                title={
                  <>
                    {cc.doc_no}
                    {cc.remark ? <Text style={s.remark}>{` · ${cc.remark}`}</Text> : null}
                  </>
                }
                onPress={() => void openCount(cc)}
                disabled={busy}
                testID={`count-${cc.doc_no}`}
              />
            ))}
          </>
        )}
      </Screen>
    );
  }

  const countedHere = linesHere.filter((l) => l.counted_at || queued[keyOf(l.to_location!.id, l.item.id, l.batch_no, l.expiry_date)] !== undefined).length;
  const step = !location ? 0 : editing ? 2 : 1;

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={["Location", "Item", "Count"]}
      step={step}
      footer={
        editing ? (
          <View style={{ flexDirection: "row", gap: space.sm }}>
            <Button title="Cancel" variant="secondary" onPress={() => setEditing(null)} style={{ flex: 1 }} />
            <Button title="OK, record" icon="check" onPress={() => void submitEntry()} loading={busy} testID="confirm-count" style={{ flex: 2 }} />
          </View>
        ) : undefined
      }
    >
      <ContextBar
        items={[
          { icon: "clipboard-list-outline", label: "Cycle count", value: count.doc_no, sub: count.count_locations.map((cl) => cl.location.code).join(", ") },
          ...(location ? [{ icon: "map-marker-radius" as const, label: "Location", value: location.code, sub: location.name }] : []),
        ]}
        onChange={location ? leaveLocation : leaveCount}
        changeLabel={location ? "Change location" : "Change count"}
      />

      {!location ? (
        <ScanInput label="Scan the location to count" icon="map-marker-radius" onScan={scanLocation} active={!busy} testID="scan-count-location" />
      ) : (
        <>
          <ScanInput
            label={scanCounting ? `Scan each ${editing?.item.sku_code ?? "item"}` : "Scan item barcode"}
            onScan={scanItem}
            active={(!editing || scanCounting) && !choices.length && !busy}
            testID="scan-item"
          />
          {!editing && <EachScanToggle />}

          {choices.length > 0 && choiceItem && (
            <Card title="Choose the batch on the goods" icon="layers-outline">
              {choices.map((l) => (
                <ListRow key={l.id} title={`Batch ${l.batch_no ?? "-"}`} subtitle={`Exp ${l.expiry_date ?? "-"}`} onPress={() => startEdit(choiceItem, l)} />
              ))}
              <ListRow title="Other batch" subtitle="Not on the book" icon="plus" onPress={() => startEdit(choiceItem, null)} />
            </Card>
          )}

          {editing && (
            <Card style={s.panel}>
              <View>
                <Text style={s.sku}>{editing.item.sku_code}</Text>
                <Text style={s.name}>{editing.item.name}</Text>
              </View>
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
                  <DateField label="Expiry date" value={editing.expiryDate} onChange={(v) => setEditing({ ...editing, expiryDate: v })} testID="expiry" />
                ))}
              <QtyField
                label="Counted quantity (base unit, 0 if none)"
                value={qtyText}
                onChangeText={setQtyText}
                // Not while scanning each piece: the scanner would type the next barcode into the quantity
                autoFocus={!scanCounting && (editing.fixed || !(editing.item.is_batch_managed || editing.item.is_expiry_managed))}
                onSubmitEditing={() => void submitEntry()}
                testID="qty"
              />
            </Card>
          )}

          <Card
            title={`Lines at this location (${linesHere.length})`}
            icon="format-list-checks"
            right={linesHere.length > 0 ? <Pill tone={countedHere === linesHere.length ? "success" : "neutral"} text={`${countedHere}/${linesHere.length}`} /> : undefined}
          >
            {linesHere.length === 0 && <Text style={s.muted}>No stock on book; record whatever goods you find</Text>}
            {linesHere.map((l, i) => {
              const status = lineStatus(l);
              return (
                <View key={l.id}>
                  {i > 0 && <Divider />}
                  <View style={s.lineRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.lineTitle}>{l.item.sku_code}</Text>
                      <Text style={s.muted}>
                        {[l.batch_no && `Batch ${l.batch_no}`, l.qty_planned !== null && `Book ${fmtQty(l.qty_planned)}`].filter(Boolean).join("  ·  ") || l.item.name}
                      </Text>
                    </View>
                    <Pill tone={status.tone} text={status.text} />
                  </View>
                </View>
              );
            })}
          </Card>

          <PhotoCapture
            label="Photo of what you found"
            hint="Sent right away with the count, tagged with this location"
            onTaken={(photo) =>
              void submitOp(
                "attach",
                `Photo ${count.doc_no} ${location.code}`,
                { document_id: count.id, doc_no: count.doc_no },
                [photo.caption ? `${location.code}: ${photo.caption}` : location.code],
                [{ ...photo, caption: [location.code, photo.caption].filter(Boolean).join(": ") }],
              ).then((outcome) =>
                setNotice(
                  outcome.status === "done"
                    ? { kind: "success", text: "Photo saved" }
                    : outcome.status === "queued"
                      ? { kind: "warning", text: "Photo saved on this device; it will be sent when back online" }
                      : { kind: "error", text: `Photo not saved: ${outcome.error}` },
                ),
              )
            }
          />
        </>
      )}
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    listHeader: { fontSize: 13, fontWeight: "600", color: c.textSecondary, textTransform: "uppercase", letterSpacing: 0.6 },
    remark: { fontWeight: "400", color: c.textSecondary },
    panel: { borderColor: c.primary, borderWidth: 2, borderRadius: radius.lg },
    sku: { fontSize: 22, fontWeight: "800", color: c.text },
    name: { fontSize: 15, color: c.textSecondary },
    muted: { fontSize: 13, color: c.textMuted },
    lineRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 8 },
    lineTitle: { fontSize: 16, fontWeight: "600", color: c.text },
  });
