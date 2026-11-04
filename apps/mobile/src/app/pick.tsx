import { useEffect, useState } from "react";

import { ScrollView, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import { Banner, Button, Card, Field, Row, colors, styles, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { fetchOpenPicks, fetchPick, fmtQty } from "@/lib/inbound";
import type { DocumentSummary, Pick, PickLine } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";

type Step = "bin" | "item" | "qty";

const same = (a: string, b: string) => a.trim().toUpperCase() === b.trim().toUpperCase();

/** Guided picking in bin order: scan bin -> scan item -> confirm quantity (short picks allowed); post once every line is confirmed */
export default function PickScreen() {
  const findItem = useMasterData((s) => s.findItem);
  const submitOp = useQueue((s) => s.submit);

  const [picks, setPicks] = useState<DocumentSummary[] | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  // Picked quantities confirmed on this device (including those still in the queue)
  const [local, setLocal] = useState<Record<string, number>>({});
  const [skipped, setSkipped] = useState<string[]>([]);
  const [step, setStep] = useState<Step>("bin");
  const [qtyText, setQtyText] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  const loadList = async () => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchOpenPicks();
      setPicks(data);
      if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached pick list" });
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadList();
  }, []);

  const openPick = async (summary: DocumentSummary) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchPick(summary.id, summary.doc_no);
      setPick(data);
      setLocal({});
      setSkipped([]);
      setStep("bin");
      setNotice(cachedAt ? { kind: "warning", text: "Offline: using the cached pick list; confirmations are saved on this device and submitted when back online" } : null);
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const isDone = (l: PickLine) => l.confirmed_at !== null || l.id in local;
  const remaining = pick ? pick.lines.filter((l) => !isDone(l)) : [];
  // Skipped lines go to the end
  const current = remaining.find((l) => !skipped.includes(l.id)) ?? remaining[0] ?? null;
  const doneCount = pick ? pick.lines.length - remaining.length : 0;

  const scanBin = (code: string) => {
    if (!current?.from_location) return;
    if (!same(code, current.from_location.code)) {
      return setNotice({ kind: "error", text: `Wrong bin: go to ${current.from_location.code}, scanned ${code}` });
    }
    setNotice(null);
    setStep("item");
  };

  const scanItem = (code: string) => {
    if (!current) return;
    const match = findItem(code);
    if (!match || match.item.id !== current.item.id) {
      return setNotice({ kind: "error", text: `Wrong item: pick ${current.item.sku_code} ${current.item.name}` });
    }
    setNotice(null);
    setQtyText(fmtQty(current.qty_planned));
    setStep("qty");
  };

  const confirmQty = async () => {
    if (!pick || !current) return;
    const qty = Number(qtyText.trim());
    if (qtyText.trim() === "" || !Number.isFinite(qty) || qty < 0) {
      return setNotice({ kind: "error", text: "Enter the picked quantity (0 if none)" });
    }
    if (qty > current.qty_planned) {
      return setNotice({ kind: "error", text: `Pick at most ${fmtQty(current.qty_planned)}; over-picking is not allowed` });
    }
    setBusy(true);
    const line = current;
    const outcome = await submitOp("pick_confirm", `Pick ${pick.doc_no} ${line.from_location?.code} ${line.item.sku_code}`, {
      pick_id: pick.id,
      line_id: line.id,
      qty,
    });
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });
    setLocal((m) => ({ ...m, [line.id]: qty }));
    setSkipped((s) => s.filter((id) => id !== line.id));
    setStep("bin");
    const short = qty < line.qty_planned ? ` (short ${fmtQty(line.qty_planned - qty)})` : "";
    setNotice(
      outcome.status === "done"
        ? { kind: short ? "warning" : "success", text: `${line.item.sku_code} picked ${fmtQty(qty)}${short}` }
        : { kind: "warning", text: `${line.item.sku_code} picked ${fmtQty(qty)}${short}; saved on this device, submitted when back online` },
    );
  };

  const skip = () => {
    if (!current) return;
    setSkipped((s) => [...s.filter((id) => id !== current.id), current.id]);
    setStep("bin");
    setNotice({ kind: "info", text: `Skipped ${current.from_location?.code}; come back to it last` });
  };

  const finish = async () => {
    if (!pick) return;
    setBusy(true);
    const outcome = await submitOp("pick_post", `Post pick ${pick.doc_no}`, { pick_id: pick.id });
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Posting rejected: ${outcome.error}` });
    setPick(null);
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `Pick list ${outcome.docNo} done; goods moved to staging` }
        : { kind: "warning", text: `Pick completion saved on this device; it will be posted when back online (${outcome.reason})` },
    );
    void loadList();
  };

  if (!pick) {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <Banner notice={notice} />
        <Text style={styles.title}>Choose a pick list</Text>
        {picks?.length === 0 && <Text style={styles.hint}>No pick lists to pick (created when a sales order is allocated in the web console)</Text>}
        {picks?.map((p) => (
          <Button key={p.id} variant="default" title={p.doc_no} onPress={() => void openPick(p)} testID={`pick-${p.doc_no}`} />
        ))}
        <Button title="Refresh" variant="default" onPress={() => void loadList()} loading={busy} />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Banner notice={notice} />
      <Card>
        <Row label="Pick list" value={pick.doc_no} />
        <Row label="Progress" value={`${doneCount} / ${pick.lines.length} lines`} />
        <Row label="Drop at" value={pick.location?.code ?? ""} />
      </Card>

      {current ? (
        <Card>
          <Text style={[styles.title, { fontSize: 26 }]} testID="target-bin">
            {current.from_location?.code}
          </Text>
          <Text style={{ fontSize: 17 }}>
            {current.item.sku_code} {current.item.name}
          </Text>
          {current.batch_no && <Row label="Batch" value={current.batch_no} />}
          {current.expiry_date && <Row label="Expiry" value={current.expiry_date} />}
          <Row label="To pick" value={`${fmtQty(current.qty_planned)} ${current.uom.code}`} />

          {step === "bin" && <ScanInput label="① Scan bin" onScan={scanBin} active={!busy} testID="scan-bin" />}
          {step === "item" && <ScanInput label="② Scan item" onScan={scanItem} active={!busy} testID="scan-item" />}
          {step === "qty" && (
            <>
              <Field
                label="③ Picked quantity (0 if none)"
                value={qtyText}
                onChangeText={setQtyText}
                keyboardType="decimal-pad"
                selectTextOnFocus
                autoFocus
                onSubmitEditing={() => void confirmQty()}
                testID="qty"
              />
              <Button title="Confirm" onPress={() => void confirmQty()} loading={busy} testID="confirm-pick" />
            </>
          )}
          {remaining.length > 1 && <Button title="Skip this line, pick later" variant="default" onPress={skip} testID="skip" />}
        </Card>
      ) : (
        <Card>
          <Text style={styles.title}>All {pick.lines.length} lines picked</Text>
          <Button title="Finish picking (post)" onPress={() => void finish()} loading={busy} testID="finish-pick" />
        </Card>
      )}

      <Card>
        {pick.lines.map((l) => {
          const qty = l.id in local ? local[l.id] : l.confirmed_at ? l.qty_actual : null;
          return (
            <View key={l.id} style={{ flexDirection: "row", gap: 8 }}>
              <Text style={{ flex: 1, fontSize: 14 }}>
                {l.from_location?.code} {l.item.sku_code}
                {l.batch_no ? ` ${l.batch_no}` : ""}
              </Text>
              <Text style={{ fontSize: 14, color: qty === null ? colors.subtle : qty < l.qty_planned ? colors.danger : colors.success }}>
                {qty === null ? `To pick ${fmtQty(l.qty_planned)}` : `Picked ${fmtQty(qty)}/${fmtQty(l.qty_planned)}`}
              </Text>
            </View>
          );
        })}
      </Card>

      <Button title="Change pick list" variant="default" onPress={() => { setPick(null); void loadList(); }} />
    </ScrollView>
  );
}
