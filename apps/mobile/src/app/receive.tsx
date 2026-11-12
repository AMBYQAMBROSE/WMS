import { useEffect, useRef, useState } from "react";

import { useLocalSearchParams, useNavigation, usePreventRemove } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import PhotoCapture from "@/components/PhotoCapture";
import { DateField } from "@/components/DateField";
import ScanInput from "@/components/ScanInput";
import Screen, { ContextBar } from "@/components/Screen";
import { Button, Card, Divider, EachScanToggle, Field, IconButton, Pill, ProgressBar, QtyField, Stat } from "@/components/ui";
import { errorText } from "@/lib/api";
import { confirm, haptic, useNotice } from "@/lib/feedback";
import { fetchPurchaseOrder, fmtQty, parseDate, parseQty } from "@/lib/inbound";
import { removePhoto, type PhotoRef } from "@/lib/photos";
import type { Document, DocumentLine, MobileLocation } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSettings } from "@/stores/settings";
import { radius, space, useStyles, type Palette } from "@/theme";

interface Entry {
  key: number;
  line: DocumentLine;
  qty: number;
  batchNo: string | null;
  expiryDate: string | null;
}

const RECEIVABLE = ["CONFIRMED", "PARTIALLY_RECEIVED"];
let nextKey = 1;

export default function ReceiveScreen() {
  const s = useStyles(makeStyles);
  const navigation = useNavigation();
  const findItem = useMasterData((st) => st.findItem);
  const findLocation = useMasterData((st) => st.findLocation);
  const submitOp = useQueue((st) => st.submit);
  const eachScan = useSettings((st) => st.eachScanCountsOne);

  const [po, setPo] = useState<Document | null>(null);
  const [location, setLocation] = useState<MobileLocation | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editing, setEditing] = useState<DocumentLine | null>(null);
  const [qtyText, setQtyText] = useState("");
  const [batchText, setBatchText] = useState("");
  const [expiryText, setExpiryText] = useState("");
  const [notice, setNotice] = useNotice();
  const [photos, setPhotos] = useState<PhotoRef[]>([]);
  const [busy, setBusy] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  // Photos not handed to a submitted receipt are deleted when the screen goes away, so no files are orphaned
  const photosRef = useRef(photos);
  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);
  useEffect(() => () => photosRef.current.forEach((p) => void removePhoto(p.id)), []);

  // Leaving with scanned but unsubmitted lines asks first
  usePreventRemove(entries.length > 0, ({ data }) =>
    confirm("Discard this receipt?", `${entries.length} scanned line(s) have not been submitted.`, "Discard", () =>
      navigation.dispatch(data.action),
    ),
  );

  const entered = (lineId: string) => entries.filter((e) => e.line.id === lineId).reduce((sum, e) => sum + e.qty, 0);
  const left = (line: DocumentLine) => line.qty_planned - line.qty_actual - entered(line.id);

  /** submitted: the photos now belong to the queued receipt; otherwise they are discarded with the entry */
  const reset = (submitted = false) => {
    if (!submitted) photos.forEach((p) => void removePhoto(p.id));
    setPhotos([]);
    setPo(null);
    setLocation(null);
    setEntries([]);
    setEditing(null);
    setCachedAt(null);
  };

  const changePo = () => {
    if (!entries.length && !photos.length) return reset();
    confirm("Change purchase order?", "The lines and photos entered here will be discarded.", "Discard", () => {
      reset();
      setNotice(null);
    });
  };

  const scanPo = async (code: string) => {
    setBusy(true);
    setNotice(null);
    await loadPo(code);
  };

  /** Fetch the order and show it; state is only set after the fetch, so the mount effect below may call it */
  const loadPo = async (code: string) => {
    try {
      const { data, cachedAt: cached } = await fetchPurchaseOrder(code);
      if (!RECEIVABLE.includes(data.status)) {
        setNotice({ kind: "error", text: `Purchase order ${data.doc_no} is ${data.status}; cannot receive` });
        return;
      }
      setPo(data);
      setCachedAt(cached ?? null);
      if (cached) {
        setNotice({
          kind: "warning",
          text: `Offline: using the purchase order cached at ${new Date(cached).toLocaleString()}; received quantities may be out of date, the server decides on submit`,
        });
      }
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  // Opened from the home screen's scan field with a purchase order number
  const params = useLocalSearchParams<{ doc?: string }>();
  useEffect(() => {
    if (params.doc) void loadPo(params.doc);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on mount
  }, []);

  const scanLocation = (code: string) => {
    const loc = findLocation(code);
    if (!loc) return setNotice({ kind: "error", text: `Location ${code} not found (for new locations, update master data on the home screen first)` });
    if (loc.is_locked) return setNotice({ kind: "error", text: `Location ${loc.code} is locked` });
    setNotice(null);
    haptic("tick");
    setLocation(loc);
  };

  const scanItem = (code: string) => {
    if (!po) return;
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code} (for new items, update master data on the home screen first)` });
    const lines = po.lines.filter((l) => l.item.id === match.item.id);
    if (!lines.length) return setNotice({ kind: "error", text: `${match.item.sku_code} ${match.item.name} is not on this purchase order` });
    const line = lines.find((l) => left(l) > 0) ?? lines[0];
    if (left(line) <= 0) return setNotice({ kind: "warning", text: `${line.item.sku_code} is fully received` });
    // A GS1 carton code carries its own quantity, batch and expiry: no each-scan counting, nothing to type
    const lot = match.lot;
    if (eachScan && !lot && !line.item.is_batch_managed && !line.item.is_expiry_managed) return addOne(line);
    setNotice(null);
    haptic("tick");
    setEditing(line);
    setQtyText(fmtQty(lot?.qty ? Math.min(lot.qty, left(line)) : left(line)));
    setBatchText(lot?.batchNo ?? "");
    setExpiryText(lot?.expiryDate ?? "");
  };

  /** Continuous scanning: one more piece on the line, consecutive scans of it add up in one entry */
  const addOne = (line: DocumentLine) => {
    const last = entries[entries.length - 1];
    const next =
      last && last.line.id === line.id && !last.batchNo && !last.expiryDate
        ? [...entries.slice(0, -1), { ...last, qty: last.qty + 1 }]
        : [...entries, { key: nextKey++, line, qty: 1, batchNo: null, expiryDate: null }];
    setEntries(next);
    const now = next.filter((e) => e.line.id === line.id).reduce((sum, e) => sum + e.qty, 0);
    setNotice({ kind: "success", text: `${line.item.sku_code} +1, now ${fmtQty(now)} ${line.uom.code}` }, { silent: true });
    haptic("tick");
  };

  const confirmEntry = () => {
    if (!editing) return;
    const qty = parseQty(qtyText);
    if (qty === null) return setNotice({ kind: "error", text: "Quantity must be a number greater than 0 (up to 4 decimals)" });
    const batchNo = batchText.trim() || null;
    if (editing.item.is_batch_managed && !batchNo) return setNotice({ kind: "error", text: "This item needs a batch no." });
    let expiryDate: string | null = null;
    if (editing.item.is_expiry_managed) {
      expiryDate = parseDate(expiryText);
      if (!expiryDate) return setNotice({ kind: "error", text: "Expiry date must be YYYY-MM-DD" });
    }
    if (qty > left(editing)) {
      setNotice({ kind: "warning", text: `Note: exceeds the open quantity ${fmtQty(left(editing))}; the server rejects over-receipt by default` });
    } else {
      setNotice({ kind: "success", text: `${editing.item.sku_code} × ${fmtQty(qty)} ${editing.uom.code} added` }, { silent: true });
      haptic("tick");
    }
    setEntries([...entries, { key: nextKey++, line: editing, qty, batchNo, expiryDate }]);
    setEditing(null);
  };

  const submit = async () => {
    if (!po || !location || !entries.length) return;
    setBusy(true);
    const outcome = await submitOp("receive", `Receive ${po.doc_no}`, {
      po_id: po.id,
      location_id: location.id,
      lines: entries.map((e) => ({
        po_line_id: e.line.id,
        qty: e.qty,
        batch_no: e.batchNo,
        expiry_date: e.expiryDate,
      })),
    }, [
      `Into ${location.code}`,
      ...entries.map(
        (e) => `${e.line.item.sku_code} × ${fmtQty(e.qty)} ${e.line.uom.code}${e.batchNo ? ` batch ${e.batchNo}` : ""}`,
      ),
      ...(photos.length ? [`${photos.length} photo(s)`] : []),
    ], photos);
    setBusy(false);
    if (outcome.status === "failed") {
      setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });
      return;
    }
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `Received, document no. ${outcome.docNo}` }
        : { kind: "warning", text: `Saved on this device; it will be submitted when back online (${outcome.reason})` },
    );
    reset(true);
  };

  const step = !po ? 0 : !location ? 1 : 2;

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={["Order", "Location", "Items"]}
      step={step}
      footer={
        po && location ? (
          <Button
            title={`Submit receipt (${entries.length} lines)`}
            icon="check-circle-outline"
            onPress={() => void submit()}
            disabled={!entries.length || !!editing}
            loading={busy}
            testID="submit-receive"
          />
        ) : undefined
      }
    >
      {!po && (
        <ScanInput label="Scan purchase order no." icon="file-document-outline" onScan={(c) => void scanPo(c)} active={!busy} testID="scan-po" />
      )}

      {po && (
        <ContextBar
          items={[
            { icon: "file-document-outline", label: "Purchase order", value: po.doc_no, sub: po.partner?.name ?? "" },
            ...(location ? [{ icon: "map-marker-radius" as const, label: "Receiving location", value: location.code, sub: location.name }] : []),
          ]}
          onChange={changePo}
          changeLabel="Change"
          badge={cachedAt ? <Pill tone="warning" icon="cloud-off-outline" text={`Cached ${new Date(cachedAt).toLocaleTimeString()}`} /> : undefined}
        />
      )}

      {po && !location && <ScanInput label="Scan receiving location" icon="map-marker-radius" onScan={scanLocation} testID="scan-location" />}

      {po && location && (
        <>
          <ScanInput label="Scan item barcode" onScan={scanItem} active={!editing && !busy} testID="scan-item" />
          {/* Out of the way while a quantity is entered, so the panel sits right under the scan field */}
          {!editing && <EachScanToggle />}

          {editing && (
            <Card style={s.panel}>
              <View>
                <Text style={s.sku}>{editing.item.sku_code}</Text>
                <Text style={s.name}>{editing.item.name}</Text>
              </View>
              <View style={{ flexDirection: "row" }}>
                <Stat label="Open" value={`${fmtQty(left(editing))} ${editing.uom.code}`} />
                <Stat label="Ordered" value={`${fmtQty(editing.qty_planned)} ${editing.uom.code}`} />
              </View>
              {editing.item.is_batch_managed && (
                <Field label="Batch no. (scannable)" value={batchText} onChangeText={setBatchText} autoFocus testID="batch" />
              )}
              {editing.item.is_expiry_managed && (
                <DateField label="Expiry date" value={expiryText} onChange={setExpiryText} testID="expiry" />
              )}
              <QtyField
                label="Received now"
                unit={editing.uom.code}
                value={qtyText}
                onChangeText={setQtyText}
                min={0}
                autoFocus={!editing.item.is_batch_managed}
                onSubmitEditing={confirmEntry}
                testID="qty"
              />
              <View style={{ flexDirection: "row", gap: space.sm }}>
                <Button title="Cancel" variant="secondary" onPress={() => setEditing(null)} style={{ flex: 1 }} />
                <Button title="Add" icon="plus" onPress={confirmEntry} testID="confirm-entry" style={{ flex: 2 }} />
              </View>
            </Card>
          )}

          {entries.length > 0 && (
            <Card title={`This receipt (${entries.length} lines)`} icon="playlist-check">
              {entries.map((e, i) => (
                <View key={e.key}>
                  {i > 0 && <Divider />}
                  <View style={s.entry}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.entryTitle}>
                        {e.line.item.sku_code} × {fmtQty(e.qty)} {e.line.uom.code}
                      </Text>
                      {(e.batchNo || e.expiryDate) && (
                        <Text style={s.entrySub}>
                          {[e.batchNo && `Batch ${e.batchNo}`, e.expiryDate && `Exp ${e.expiryDate}`].filter(Boolean).join("  ·  ")}
                        </Text>
                      )}
                    </View>
                    <IconButton icon="trash-can-outline" tone="danger" label={`Delete ${e.line.item.sku_code}`} onPress={() => setEntries(entries.filter((x) => x.key !== e.key))} />
                  </View>
                </View>
              ))}
            </Card>
          )}

          <Card title="Order lines" icon="format-list-bulleted">
            {po.lines.map((line, i) => {
              const now = entered(line.id);
              const open = line.qty_planned - line.qty_actual;
              const done = line.qty_actual + now;
              const full = now >= open && open > 0;
              return (
                <View key={line.id} style={{ gap: 6 }}>
                  {i > 0 && <Divider />}
                  <View style={s.lineHead}>
                    <Text style={s.lineTitle} numberOfLines={1}>
                      {line.item.sku_code} <Text style={s.lineName}>{line.item.name}</Text>
                    </Text>
                    <Text style={[s.lineQty, full && s.lineDone]}>
                      {`Now ${fmtQty(now)} / open ${fmtQty(open)} ${line.uom.code}`}
                    </Text>
                  </View>
                  <ProgressBar value={line.qty_planned ? done / line.qty_planned : 0} tone={full || open <= 0 ? "success" : "primary"} />
                </View>
              );
            })}
          </Card>

          <PhotoCapture photos={photos} onChange={setPhotos} />
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
    entry: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 2 },
    entryTitle: { fontSize: 16, fontWeight: "600", color: c.text, fontVariant: ["tabular-nums"] },
    entrySub: { fontSize: 13, color: c.textMuted },
    lineHead: { gap: 2, paddingTop: 4 },
    lineTitle: { fontSize: 15, fontWeight: "700", color: c.text },
    lineName: { fontWeight: "400", color: c.textSecondary },
    lineQty: { fontSize: 13, color: c.textMuted, fontVariant: ["tabular-nums"] },
    lineDone: { color: c.successText, fontWeight: "600" },
  });
