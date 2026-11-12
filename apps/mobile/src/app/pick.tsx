import { useEffect, useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen from "@/components/Screen";
import { Button, Card, Divider, EmptyState, ListRow, Pill, ProgressBar, QtyField } from "@/components/ui";
import { errorText } from "@/lib/api";
import { confirm, haptic, useNotice } from "@/lib/feedback";
import { fetchOpenPicks, fetchPick, fmtQty } from "@/lib/inbound";
import type { DocumentSummary, Pick, PickLine } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useTasks } from "@/stores/tasks";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

type Step = "bin" | "item" | "qty";
const STEP_INDEX: Record<Step, number> = { bin: 0, item: 1, qty: 2 };

const same = (a: string, b: string) => a.trim().toUpperCase() === b.trim().toUpperCase();

/** Guided picking in bin order: scan bin -> scan item -> confirm quantity (short picks allowed); post once every line is confirmed */
export default function PickScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const findItem = useMasterData((st) => st.findItem);
  const submitOp = useQueue((st) => st.submit);

  const params = useLocalSearchParams<{ doc?: string }>();
  const [picks, setPicks] = useState<DocumentSummary[] | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  // Picked quantities confirmed on this device (including those still in the queue)
  const [local, setLocal] = useState<Record<string, number>>({});
  const [skipped, setSkipped] = useState<string[]>([]);
  const [step, setStep] = useState<Step>("bin");
  const [qtyText, setQtyText] = useState("");
  const [notice, setNotice] = useNotice();
  const [showLines, setShowLines] = useState(false);
  // Starts busy: the list loads on mount
  const [busy, setBusy] = useState(true);

  const applyList = ({ data, cachedAt }: Awaited<ReturnType<typeof fetchOpenPicks>>) => {
    setPicks(data);
    if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached pick list" }, { silent: true });
  };
  const failList = (error: unknown) => setNotice({ kind: "error", text: errorText(error) });

  const loadList = async () => {
    setBusy(true);
    try {
      applyList(await fetchOpenPicks());
    } catch (error) {
      failList(error);
    } finally {
      setBusy(false);
    }
  };

  const openPick = async (summary: DocumentSummary) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchPick(summary.id, summary.doc_no);
      setPick(data);
      setLocal({});
      setSkipped([]);
      setStep("bin");
      setNotice(
        cachedAt
          ? { kind: "warning", text: "Offline: using the cached pick list; confirmations are saved on this device and submitted when back online" }
          : null,
      );
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  // On mount, state is set from the promise callbacks rather than synchronously in the effect
  useEffect(() => {
    useTasks.getState().seen("pick");
    fetchOpenPicks()
.then((result) => {
        applyList(result);
        // Opened from the home screen's scan field with this document's number
        const wanted = params.doc && result.data.find((d) => d.doc_no.toUpperCase() === params.doc!.toUpperCase());
        if (wanted) void openPick(wanted);
      }, failList)
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, []);

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
    haptic("tick");
    setStep("item");
  };

  const scanItem = (code: string) => {
    if (!current) return;
    const match = findItem(code);
    if (!match || match.item.id !== current.item.id) {
      return setNotice({ kind: "error", text: `Wrong item: pick ${current.item.sku_code} ${current.item.name}` });
    }
    if (match.lot?.batchNo && current.batch_no && match.lot.batchNo !== current.batch_no) {
      return setNotice({ kind: "error", text: `Wrong batch: pick batch ${current.batch_no}, this is ${match.lot.batchNo}` });
    }
    setNotice(null);
    haptic("tick");
    setQtyText(fmtQty(current.qty_planned));
    setStep("qty");
  };

  const confirmQty = async () => {
    if (!pick || !current || busy) return;
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
    }, [`${line.item.sku_code} × ${fmtQty(qty)} of ${fmtQty(line.qty_planned)} from ${line.from_location?.code ?? ""}`]);
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });
    setLocal((m) => ({ ...m, [line.id]: qty }));
    setSkipped((sk) => sk.filter((id) => id !== line.id));
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
    setSkipped((sk) => [...sk.filter((id) => id !== current.id), current.id]);
    setStep("bin");
    setNotice({ kind: "info", text: `Skipped ${current.from_location?.code}; come back to it last` }, { silent: true });
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

  const leavePick = () => {
    const go = () => {
      setPick(null);
      void loadList();
    };
    if (doneCount === 0 || !remaining.length) return go();
    confirm("Leave this pick list?", "Confirmed lines are kept; you can continue it later.", "Leave", go);
  };

  if (!pick) {
    return (
      <Screen
        notice={notice}
        onDismiss={() => setNotice(null)}
        refreshControl={<RefreshControl refreshing={busy && picks !== null} onRefresh={() => void loadList()} colors={[c.primary]} tintColor={c.primary} />}
        footer={<Button title="Refresh" variant="secondary" icon="refresh" onPress={() => void loadList()} loading={busy} />}
      >
        {picks === null ? (
          <EmptyState icon="cart-outline" title="Loading pick lists…" />
        ) : picks.length === 0 ? (
          <EmptyState
            icon="cart-check"
            title="Nothing to pick"
            text="Pick lists appear here when a sales order is allocated in the web console. Pull down to check again."
          />
        ) : (
          <>
            <ScanInput
              label="Scan the pick list"
              icon="file-document-outline"
              onScan={(code) => {
                const found = picks.find((p) => p.doc_no.toUpperCase() === code.trim().toUpperCase());
                if (found) void openPick(found);
                else setNotice({ kind: "error", text: `${code} is not an open pick list. Pull down to refresh the list.` });
              }}
              active={!busy}
              testID="scan-pick-list"
            />
            <Text style={s.listHeader}>Or choose one</Text>
            {picks.map((p) => (
              <ListRow
                key={p.id}
                icon="cart-outline"
                title={p.doc_no}
                subtitle={p.remark || undefined}
                onPress={() => void openPick(p)}
                disabled={busy}
                testID={`pick-${p.doc_no}`}
              />
            ))}
          </>
        )}
      </Screen>
    );
  }

  const stepLabel = { bin: "Go to the bin and scan it", item: "Scan the item", qty: "Confirm the quantity" }[step];
  const wrong = notice?.kind === "error";

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={current ? ["Bin", "Item", "Qty"] : undefined}
      step={STEP_INDEX[step]}
      footer={
        current ? (
          step === "qty" ? (
            <Button title="Confirm pick" icon="check" onPress={() => void confirmQty()} loading={busy} testID="confirm-pick" />
          ) : remaining.length > 1 ? (
            <Button title="Skip this line, pick later" variant="secondary" icon="debug-step-over" onPress={skip} testID="skip" />
          ) : undefined
        ) : (
          <Button title="Finish picking (post)" icon="flag-checkered" onPress={() => void finish()} loading={busy} testID="finish-pick" />
        )
      }
    >
      <View style={s.progressHead}>
        <View style={{ flex: 1 }}>
          <Text style={s.docNo}>{pick.doc_no}</Text>
          <Text style={s.muted}>Drop at {pick.location?.code ?? "-"}</Text>
        </View>
        <Text style={s.progressText}>
          {doneCount}
          <Text style={s.muted}>{` / ${pick.lines.length} lines`}</Text>
        </Text>
      </View>
      <ProgressBar value={pick.lines.length ? doneCount / pick.lines.length : 0} tone={current ? "primary" : "success"} />

      {current ? (
        <View style={[s.hero, wrong && { borderColor: c.danger, backgroundColor: c.dangerTint }]}>
          <Text style={s.heroLabel}>{step === "bin" ? "GO TO BIN" : "BIN"}</Text>
          <Text style={[s.heroBin, wrong && { color: c.dangerText }]} testID="target-bin" numberOfLines={2} adjustsFontSizeToFit minimumFontScale={0.6}>
            {current.from_location?.code}
          </Text>
          <View style={s.heroDivider} />
          <View style={s.heroRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.heroSku}>{current.item.sku_code}</Text>
              <Text style={s.heroName} numberOfLines={2}>
                {current.item.name}
              </Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={s.heroLabel}>PICK</Text>
              <Text style={s.heroQty}>
                {fmtQty(current.qty_planned)}
                <Text style={s.heroUom}>{` ${current.uom.code}`}</Text>
              </Text>
            </View>
          </View>
          {(current.batch_no || current.expiry_date || skipped.includes(current.id)) && (
            <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
              {current.batch_no && <Pill tone="info" icon="layers-outline" text={`Batch ${current.batch_no}`} />}
              {current.expiry_date && <Pill tone="warning" icon="calendar-clock" text={`Exp ${current.expiry_date}`} />}
              {skipped.includes(current.id) && <Pill icon="debug-step-over" text="Skipped earlier" />}
            </View>
          )}
        </View>
      ) : (
        <Card>
          <EmptyState icon="check-decagram" title={`All ${pick.lines.length} lines picked`} text="Post the pick list to move the goods to staging." />
        </Card>
      )}

      {current && (
        <View style={{ gap: space.sm }}>
          <Text style={s.stepHint}>{stepLabel}</Text>
          {step === "bin" && <ScanInput label="Scan bin" icon="map-marker-radius" onScan={scanBin} active={!busy} testID="scan-bin" />}
          {step === "item" && <ScanInput label="Scan item" onScan={scanItem} active={!busy} testID="scan-item" />}
          {step === "qty" && (
            <Card>
              <QtyField
                label="Picked quantity (0 if none)"
                unit={current.uom.code}
                value={qtyText}
                onChangeText={setQtyText}
                autoFocus
                onSubmitEditing={() => void confirmQty()}
                testID="qty"
              />
            </Card>
          )}
        </View>
      )}

      <Card>
        <Pressable accessibilityRole="button" onPress={() => setShowLines((v) => !v)} style={s.linesToggle}>
          <Text style={s.linesTitle}>All lines ({pick.lines.length})</Text>
          <MaterialCommunityIcons name={showLines ? "chevron-up" : "chevron-down"} size={24} color={c.textMuted} />
        </Pressable>
        {showLines &&
          pick.lines.map((l, i) => {
            const qty = l.id in local ? local[l.id] : l.confirmed_at ? l.qty_actual : null;
            const isCurrent = current?.id === l.id;
            return (
              <View key={l.id}>
                {i > 0 && <Divider />}
                <View style={[s.lineRow, isCurrent && s.lineCurrent]}>
                  <MaterialCommunityIcons
                    name={qty === null ? (isCurrent ? "arrow-right-circle" : "circle-outline") : qty < l.qty_planned ? "alert-circle" : "check-circle"}
                    size={20}
                    color={qty === null ? (isCurrent ? c.primaryText : c.textMuted) : qty < l.qty_planned ? c.dangerText : c.successText}
                  />
                  <Text style={s.lineText} numberOfLines={1}>
                    <Text style={{ fontWeight: "700" }}>{l.from_location?.code}</Text> {l.item.sku_code}
                    {l.batch_no ? ` ${l.batch_no}` : ""}
                  </Text>
                  <Text style={[s.lineQty, { color: qty === null ? c.textMuted : qty < l.qty_planned ? c.dangerText : c.successText }]}>
                    {qty === null ? `To pick ${fmtQty(l.qty_planned)}` : `Picked ${fmtQty(qty)}/${fmtQty(l.qty_planned)}`}
                  </Text>
                </View>
              </View>
            );
          })}
      </Card>

      <Button title="Change pick list" variant="ghost" icon="swap-horizontal" onPress={leavePick} />
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    listHeader: { fontSize: 13, fontWeight: "600", color: c.textSecondary, textTransform: "uppercase", letterSpacing: 0.6 },
    progressHead: { flexDirection: "row", alignItems: "flex-end", gap: space.md },
    docNo: { fontSize: 17, fontWeight: "700", color: c.text },
    muted: { fontSize: 13, color: c.textMuted, fontWeight: "400" },
    progressText: { fontSize: 22, fontWeight: "800", color: c.text, fontVariant: ["tabular-nums"] },
    hero: {
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      borderWidth: 2,
      borderColor: c.primary,
      padding: space.lg,
      gap: space.sm,
    },
    heroLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 1, color: c.textMuted },
    heroBin: { fontSize: 40, fontWeight: "800", color: c.primaryText, letterSpacing: -0.5, fontVariant: ["tabular-nums"] },
    heroDivider: { height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginVertical: space.xs },
    heroRow: { flexDirection: "row", alignItems: "flex-end", gap: space.md },
    heroSku: { fontSize: 20, fontWeight: "700", color: c.text },
    heroName: { fontSize: 15, color: c.textSecondary },
    heroQty: { fontSize: 36, fontWeight: "800", color: c.text, fontVariant: ["tabular-nums"] },
    heroUom: { fontSize: 16, fontWeight: "600", color: c.textMuted },
    stepHint: { fontSize: 13, fontWeight: "600", color: c.textSecondary, textTransform: "uppercase", letterSpacing: 0.6 },
    linesToggle: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 32 },
    linesTitle: { fontSize: 16, fontWeight: "600", color: c.text },
    lineRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 10, paddingHorizontal: 4, borderRadius: radius.sm },
    lineCurrent: { backgroundColor: c.primaryTint },
    lineText: { flex: 1, fontSize: 14, color: c.text },
    lineQty: { fontSize: 13, fontWeight: "600", fontVariant: ["tabular-nums"] },
  });
