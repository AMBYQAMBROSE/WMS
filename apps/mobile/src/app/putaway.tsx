import { useEffect, useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen from "@/components/Screen";
import { Button, Card, Divider, EmptyState, ListRow, Pill, ProgressBar, QtyField } from "@/components/ui";
import { errorText } from "@/lib/api";
import { confirm, haptic, useNotice } from "@/lib/feedback";
import { fetchOpenPutawaySheets, fetchPutawaySheet, fmtQty, parseQty } from "@/lib/inbound";
import type { DocumentSummary, MobileLocation, PutawayLine, PutawaySheet } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

type Step = "item" | "bin" | "qty";
const STEP_INDEX: Record<Step, number> = { item: 0, bin: 1, qty: 2 };

const same = (a: string, b: string) => a.trim().toUpperCase() === b.trim().toUpperCase();

/**
 * Putaway by sheet: a receipt posted into a dock makes a putaway sheet. Scan the sheet number (or pick it from the
 * list) -> scan an item on the dock -> take it to the suggested bin (or any bin) and scan the bin -> confirm the
 * quantity. Less than the line's quantity leaves the rest open for another bin. Post once everything is put away.
 */
export default function PutawayScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const router = useRouter();
  const params = useLocalSearchParams<{ doc?: string }>();
  const findItem = useMasterData((st) => st.findItem);
  const findLocation = useMasterData((st) => st.findLocation);
  const submitOp = useQueue((st) => st.submit);

  const [sheets, setSheets] = useState<DocumentSummary[] | null>(null);
  const [sheet, setSheet] = useState<PutawaySheet | null>(null);
  // Quantities put away on this device per line (including puts still in the queue)
  const [local, setLocal] = useState<Record<string, number>>({});
  const [lineId, setLineId] = useState<string | null>(null);
  const [bin, setBin] = useState<MobileLocation | null>(null);
  const [step, setStep] = useState<Step>("item");
  const [qtyText, setQtyText] = useState("");
  const [notice, setNotice] = useNotice();
  const [showLines, setShowLines] = useState(false);
  const [busy, setBusy] = useState(true);

  const applyList = ({ data, cachedAt }: Awaited<ReturnType<typeof fetchOpenPutawaySheets>>) => {
    setSheets(data);
    if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached list of putaway sheets" }, { silent: true });
  };
  const failList = (error: unknown) => setNotice({ kind: "error", text: errorText(error) });

  const loadList = async () => {
    setBusy(true);
    try {
      applyList(await fetchOpenPutawaySheets());
    } catch (error) {
      failList(error);
    } finally {
      setBusy(false);
    }
  };

  const openSheet = async (summary: DocumentSummary) => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchPutawaySheet(summary.id, summary.doc_no);
      if (data.status !== "TO_PUT_AWAY") {
        setNotice({ kind: "error", text: `Putaway sheet ${data.doc_no} is ${data.status.toLowerCase().replace(/_/g, " ")}; nothing to put away` });
        return;
      }
      setSheet(data);
      setLocal({});
      setLineId(null);
      setBin(null);
      setStep("item");
      setNotice(
        cachedAt
          ? { kind: "warning", text: "Offline: using the cached sheet; puts are saved on this device and submitted when back online" }
          : null,
      );
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    fetchOpenPutawaySheets()
.then((result) => {
        applyList(result);
        // Opened from the home screen's scan field with this document's number
        const wanted = params.doc && result.data.find((d) => d.doc_no.toUpperCase() === params.doc!.toUpperCase());
        if (wanted) void openSheet(wanted);
      }, failList)
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, []);

  /** The sheet barcode at the top of every printed page holds its number */
  const scanSheet = (code: string) => {
    const found = sheets?.find((x) => same(x.doc_no, code));
    if (!found) {
      return setNotice({ kind: "error", text: `${code} is not an open putaway sheet. Pull down to refresh the list.` });
    }
    haptic("tick");
    void openSheet(found);
  };

  const left = (l: PutawayLine) => (l.confirmed_at ? 0 : l.qty_planned - (local[l.id] ?? 0));
  const open = sheet ? sheet.lines.filter((l) => left(l) > 0) : [];
  const current = open.find((l) => l.id === lineId) ?? null;
  const total = sheet ? sheet.lines.reduce((sum, l) => sum + l.qty_planned, 0) : 0;
  const done = total - open.reduce((sum, l) => sum + left(l), 0);

  const scanItem = (code: string) => {
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code}` });
    // The line on show first, then the first open line of that item
    const line = (current?.item.id === match.item.id ? current : null) ?? open.find((l) => l.item.id === match.item.id);
    if (!line) return setNotice({ kind: "error", text: `${match.item.sku_code} is not on this sheet, or already put away` });
    setLineId(line.id);
    setNotice(null);
    haptic("tick");
    setStep("bin");
  };

  const scanBin = (code: string) => {
    if (!current) return;
    const location = findLocation(code);
    if (!location) return setNotice({ kind: "error", text: `Unknown location ${code}` });
    if (location.location_type !== "BIN") return setNotice({ kind: "error", text: `${location.code} is not a bin; put away into bins only` });
    if (location.is_locked) return setNotice({ kind: "error", text: `Bin ${location.code} is locked` });
    setBin(location);
    haptic("tick");
    setNotice(
      current.to_location && !same(current.to_location.code, location.code)
        ? { kind: "info", text: `Not the suggested bin ${current.to_location.code}; ${location.code} is fine too` }
        : null,
      { silent: true },
    );
    setQtyText(fmtQty(left(current)));
    setStep("qty");
  };

  const confirmPut = async () => {
    if (!sheet || !current || !bin || busy) return;
    const qty = parseQty(qtyText);
    if (qty === null) return setNotice({ kind: "error", text: "Enter the quantity put into the bin" });
    if (qty > left(current)) return setNotice({ kind: "error", text: `At most ${fmtQty(left(current))} ${current.uom.code} left on this line` });
    setBusy(true);
    const line = current;
    const outcome = await submitOp(
      "putaway_put",
      `Put away ${sheet.doc_no} ${line.item.sku_code} → ${bin.code}`,
      { sheet_id: sheet.id, line_id: line.id, to_location_id: bin.id, qty },
      [`${line.item.sku_code} × ${fmtQty(qty)} ${line.uom.code} into ${bin.code}`],
    );
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });
    setLocal((m) => ({ ...m, [line.id]: (m[line.id] ?? 0) + qty }));
    const rest = left(line) - qty;
    setBin(null);
    setLineId(rest > 0 ? line.id : null);
    // The rest of a partly put line goes into another bin: go straight back to scanning a bin for it
    setStep(rest > 0 ? "bin" : "item");
    const text = `${line.item.sku_code} ${fmtQty(qty)} into ${bin.code}${rest > 0 ? `; ${fmtQty(rest)} left, scan the next bin` : ""}`;
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text }
        : { kind: "warning", text: `${text}. Saved on this device, submitted when back online` },
    );
  };

  const finish = async () => {
    if (!sheet) return;
    setBusy(true);
    const outcome = await submitOp("putaway_post", `Post putaway ${sheet.doc_no}`, { sheet_id: sheet.id });
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Posting rejected: ${outcome.error}` });
    setSheet(null);
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `Putaway sheet ${outcome.docNo} done; stock is in the bins` }
        : { kind: "warning", text: `Completion saved on this device; it will be posted when back online (${outcome.reason})` },
    );
    void loadList();
  };

  const leaveSheet = () => {
    const go = () => {
      setSheet(null);
      void loadList();
    };
    if (done === 0 || !open.length) return go();
    confirm("Leave this putaway sheet?", "What was put away is kept; you can continue the sheet later.", "Leave", go);
  };

  if (!sheet) {
    return (
      <Screen
        notice={notice}
        onDismiss={() => setNotice(null)}
        refreshControl={<RefreshControl refreshing={busy && sheets !== null} onRefresh={() => void loadList()} colors={[c.primary]} tintColor={c.primary} />}
        footer={<Button title="Put away without a sheet" variant="secondary" icon="tray-arrow-down" onPress={() => router.push("/putaway-free")} testID="putaway-free" />}
      >
        <ScanInput label="Scan the putaway sheet" icon="file-document-outline" onScan={scanSheet} active={!busy && sheets !== null} testID="scan-sheet" />
        {sheets === null ? (
          <EmptyState icon="tray-arrow-down" title="Loading putaway sheets…" />
        ) : sheets.length === 0 ? (
          <EmptyState
            icon="tray-full"
            title="Nothing to put away"
            text="A putaway sheet appears here when a receipt into a dock is posted. Pull down to check again."
          />
        ) : (
          <>
            <Text style={s.listHeader}>Or choose a sheet</Text>
            {sheets.map((x) => (
              <ListRow
                key={x.id}
                icon="tray-arrow-down"
                title={x.doc_no}
                subtitle={x.remark || undefined}
                onPress={() => void openSheet(x)}
                disabled={busy}
                testID={`sheet-${x.doc_no}`}
              />
            ))}
          </>
        )}
      </Screen>
    );
  }

  const wrong = notice?.kind === "error";
  const next = current ?? open[0] ?? null;

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={open.length ? ["Item", "Bin", "Qty"] : undefined}
      step={STEP_INDEX[step]}
      footer={
        open.length ? (
          step === "qty" ? (
            <Button title="Confirm put away" icon="check" onPress={() => void confirmPut()} loading={busy} testID="confirm-put" />
          ) : step === "bin" ? (
            <Button
              title="Different item"
              variant="secondary"
              icon="arrow-left"
              onPress={() => {
                setStep("item");
                setLineId(null);
              }}
            />
          ) : undefined
        ) : (
          <Button title="Finish putaway (post)" icon="flag-checkered" onPress={() => void finish()} loading={busy} testID="finish-putaway" />
        )
      }
    >
      <View style={s.progressHead}>
        <View style={{ flex: 1 }}>
          <Text style={s.docNo}>{sheet.doc_no}</Text>
          <Text style={s.muted}>
            From {sheet.location?.code ?? "-"}
            {sheet.ref_document ? ` · ${sheet.ref_document.doc_no}` : ""}
          </Text>
        </View>
        <Text style={s.progressText}>
          {fmtQty(done)}
          <Text style={s.muted}>{` / ${fmtQty(total)}`}</Text>
        </Text>
      </View>
      <ProgressBar value={total ? done / total : 0} tone={open.length ? "primary" : "success"} />

      {next ? (
        <View style={[s.hero, wrong && { borderColor: c.danger, backgroundColor: c.dangerTint }]}>
          <Text style={s.heroLabel}>{step === "item" && !current ? "NEXT ON THE DOCK" : "ITEM"}</Text>
          <View style={s.heroRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.heroSku}>{next.item.sku_code}</Text>
              <Text style={s.heroName} numberOfLines={2}>
                {next.item.name}
              </Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={s.heroLabel}>PUT AWAY</Text>
              <Text style={s.heroQty}>
                {fmtQty(left(next))}
                <Text style={s.heroUom}>{` ${next.uom.code}`}</Text>
              </Text>
            </View>
          </View>
          <View style={s.heroDivider} />
          <Text style={s.heroLabel}>{bin ? "INTO BIN" : next.to_location ? "SUGGESTED BIN" : "BIN"}</Text>
          <Text style={[s.heroBin, wrong && { color: c.dangerText }]} testID="target-bin" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
            {bin?.code ?? next.to_location?.code ?? "Any bin"}
          </Text>
          {(next.batch_no || next.expiry_date) && (
            <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
              {next.batch_no && <Pill tone="info" icon="layers-outline" text={`Batch ${next.batch_no}`} />}
              {next.expiry_date && <Pill tone="warning" icon="calendar-clock" text={`Exp ${next.expiry_date}`} />}
            </View>
          )}
        </View>
      ) : (
        <Card>
          <EmptyState icon="check-decagram" title="Everything is put away" text="Post the sheet to move the stock into the bins." />
        </Card>
      )}

      {open.length > 0 && (
        <View style={{ gap: space.sm }}>
          {step === "item" && <ScanInput label="Scan an item from the dock" onScan={scanItem} active={!busy} testID="scan-item" />}
          {step === "bin" && <ScanInput label="Scan the bin you put it in" icon="map-marker-radius" onScan={scanBin} active={!busy} testID="scan-bin" />}
          {step === "qty" && current && (
            <Card>
              <QtyField
                label={`Quantity into ${bin?.code ?? "the bin"}`}
                unit={current.uom.code}
                value={qtyText}
                onChangeText={setQtyText}
                autoFocus
                onSubmitEditing={() => void confirmPut()}
                testID="qty"
              />
            </Card>
          )}
        </View>
      )}

      <Card>
        <Pressable accessibilityRole="button" onPress={() => setShowLines((v) => !v)} style={s.linesToggle}>
          <Text style={s.linesTitle}>All lines ({sheet.lines.length})</Text>
          <MaterialCommunityIcons name={showLines ? "chevron-up" : "chevron-down"} size={24} color={c.textMuted} />
        </Pressable>
        {showLines &&
          sheet.lines.map((l, i) => {
            const remaining = left(l);
            return (
              <View key={l.id}>
                {i > 0 && <Divider />}
                <View style={[s.lineRow, current?.id === l.id && s.lineCurrent]}>
                  <MaterialCommunityIcons
                    name={remaining > 0 ? "circle-outline" : "check-circle"}
                    size={20}
                    color={remaining > 0 ? c.textMuted : c.successText}
                  />
                  <Text style={s.lineText} numberOfLines={1}>
                    <Text style={{ fontWeight: "700" }}>{l.item.sku_code}</Text>
                    {l.batch_no ? ` ${l.batch_no}` : ""}
                    {l.to_location ? ` → ${l.to_location.code}` : ""}
                  </Text>
                  <Text style={[s.lineQty, { color: remaining > 0 ? c.textMuted : c.successText }]}>
                    {remaining > 0 ? `${fmtQty(remaining)} left` : `${fmtQty(l.confirmed_at ? l.qty_actual : l.qty_planned)} done`}
                  </Text>
                </View>
              </View>
            );
          })}
      </Card>

      <Button title="Change sheet" variant="ghost" icon="swap-horizontal" onPress={leaveSheet} />
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
    heroBin: { fontSize: 36, fontWeight: "800", color: c.primaryText, letterSpacing: -0.5, fontVariant: ["tabular-nums"] },
    heroDivider: { height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginVertical: space.xs },
    heroRow: { flexDirection: "row", alignItems: "flex-end", gap: space.md },
    heroSku: { fontSize: 20, fontWeight: "700", color: c.text },
    heroName: { fontSize: 15, color: c.textSecondary },
    heroQty: { fontSize: 36, fontWeight: "800", color: c.text, fontVariant: ["tabular-nums"] },
    heroUom: { fontSize: 16, fontWeight: "600", color: c.textMuted },
    linesToggle: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 32 },
    linesTitle: { fontSize: 16, fontWeight: "600", color: c.text },
    lineRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 10, paddingHorizontal: 4, borderRadius: radius.sm },
    lineCurrent: { backgroundColor: c.primaryTint },
    lineText: { flex: 1, fontSize: 14, color: c.text },
    lineQty: { fontSize: 13, fontWeight: "600", fontVariant: ["tabular-nums"] },
  });
