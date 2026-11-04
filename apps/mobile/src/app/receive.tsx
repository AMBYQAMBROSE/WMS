import { useState } from "react";

import { Pressable, ScrollView, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import { Banner, Button, Card, Field, Row, colors, styles, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { fetchPurchaseOrder, fmtQty, parseDate, parseQty } from "@/lib/inbound";
import type { Document, DocumentLine, MobileLocation } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";

interface Entry {
  key: number;
  line: DocumentLine;
  qty: number;
  batchNo: string | null;
  expiryDate: string | null;
}

const RECEIVABLE = ["CONFIRMED", "PARTIALLY_RECEIVED"];

export default function ReceiveScreen() {
  const findItem = useMasterData((s) => s.findItem);
  const findLocation = useMasterData((s) => s.findLocation);
  const submitOp = useQueue((s) => s.submit);

  const [po, setPo] = useState<Document | null>(null);
  const [location, setLocation] = useState<MobileLocation | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editing, setEditing] = useState<DocumentLine | null>(null);
  const [qtyText, setQtyText] = useState("");
  const [batchText, setBatchText] = useState("");
  const [expiryText, setExpiryText] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  const entered = (lineId: string) => entries.filter((e) => e.line.id === lineId).reduce((s, e) => s + e.qty, 0);
  const left = (line: DocumentLine) => line.qty_planned - line.qty_actual - entered(line.id);

  const reset = () => {
    setPo(null);
    setLocation(null);
    setEntries([]);
    setEditing(null);
  };

  const scanPo = async (code: string) => {
    setBusy(true);
    setNotice(null);
    try {
      const { data, cachedAt } = await fetchPurchaseOrder(code);
      if (!RECEIVABLE.includes(data.status)) {
        setNotice({ kind: "error", text: `Purchase order ${data.doc_no} is ${data.status}; cannot receive` });
        return;
      }
      setPo(data);
      if (cachedAt) {
        setNotice({
          kind: "warning",
          text: `Offline: using the purchase order cached at ${new Date(cachedAt).toLocaleString()}; received quantities may be out of date, the server decides on submit`,
        });
      }
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const scanLocation = (code: string) => {
    const loc = findLocation(code);
    if (!loc) return setNotice({ kind: "error", text: `Location ${code} not found (for new locations, update master data on the home screen first)` });
    if (loc.is_locked) return setNotice({ kind: "error", text: `Location ${loc.code} is locked` });
    setNotice(null);
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
    setNotice(null);
    setEditing(line);
    setQtyText(fmtQty(left(line)));
    setBatchText("");
    setExpiryText("");
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
      setNotice(null);
    }
    setEntries([...entries, { key: Date.now(), line: editing, qty, batchNo, expiryDate }]);
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
    });
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
    reset();
  };

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Banner notice={notice} />

      {!po && <ScanInput label="① Scan purchase order no." onScan={scanPo} active={!busy} testID="scan-po" />}

      {po && (
        <Card>
          <Row label="Purchase order" value={po.doc_no} />
          <Row label="Supplier" value={po.partner?.name ?? ""} />
          {location && <Row label="Receiving location" value={`${location.code} ${location.name}`} />}
        </Card>
      )}

      {po && !location && <ScanInput label="② Scan receiving location" onScan={scanLocation} testID="scan-location" />}

      {po && location && (
        <>
          <ScanInput label="③ Scan item barcode" onScan={scanItem} active={!editing && !busy} testID="scan-item" />

          {editing && (
            <Card>
              <Text style={styles.title}>
                {editing.item.sku_code} {editing.item.name}
              </Text>
              <Row label="Open" value={`${fmtQty(left(editing))} ${editing.uom.code}`} />
              {editing.item.is_batch_managed && (
                <Field label="Batch no. (scannable)" value={batchText} onChangeText={setBatchText} autoFocus testID="batch" />
              )}
              {editing.item.is_expiry_managed && (
                <Field label="Expiry date YYYY-MM-DD" value={expiryText} onChangeText={setExpiryText} testID="expiry" />
              )}
              <Field
                label={`Received now (${editing.uom.code})`}
                value={qtyText}
                onChangeText={setQtyText}
                keyboardType="decimal-pad"
                selectTextOnFocus
                autoFocus={!editing.item.is_batch_managed}
                onSubmitEditing={confirmEntry}
                testID="qty"
              />
              <View style={{ flexDirection: "row", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Button title="OK" onPress={confirmEntry} testID="confirm-entry" />
                </View>
                <View style={{ flex: 1 }}>
                  <Button title="Cancel" variant="default" onPress={() => setEditing(null)} />
                </View>
              </View>
            </Card>
          )}

          <Card>
            <Text style={styles.title}>Order lines</Text>
            {po.lines.map((line) => (
              <Row
                key={line.id}
                label={`${line.item.sku_code} ${line.item.name}`}
                value={`Now ${fmtQty(entered(line.id))} / open ${fmtQty(line.qty_planned - line.qty_actual)} ${line.uom.code}`}
              />
            ))}
          </Card>

          {entries.length > 0 && (
            <Card>
              <Text style={styles.title}>This receipt ({entries.length} lines)</Text>
              {entries.map((e) => (
                <View key={e.key} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={{ flex: 1, fontSize: 15 }}>
                    {e.line.item.sku_code} × {fmtQty(e.qty)} {e.line.uom.code}
                    {e.batchNo ? `  Batch ${e.batchNo}` : ""}
                    {e.expiryDate ? `  Exp ${e.expiryDate}` : ""}
                  </Text>
                  <Pressable onPress={() => setEntries(entries.filter((x) => x.key !== e.key))}>
                    <Text style={{ color: colors.danger, fontSize: 15 }}>Delete</Text>
                  </Pressable>
                </View>
              ))}
            </Card>
          )}

          <Button
            title={`Submit receipt (${entries.length} lines)`}
            onPress={submit}
            disabled={!entries.length || !!editing}
            loading={busy}
            testID="submit-receive"
          />
        </>
      )}

      {po && <Button title="Change purchase order" variant="default" onPress={reset} />}
    </ScrollView>
  );
}
