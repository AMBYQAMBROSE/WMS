import { useEffect, useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen from "@/components/Screen";
import { Button, Card, Divider, EmptyState, Field, ListRow, Pill, ProgressBar } from "@/components/ui";
import { errorText } from "@/lib/api";
import { haptic, useNotice } from "@/lib/feedback";
import { fetchLoadingHistory, fetchLoadingShipments, fetchShipment, fmtQty, lookupDocument, shipmentForOrder } from "@/lib/inbound";
import type { DocumentSummary, LoadingHistory, Shipment, ShipmentInfo, ShipmentLine } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

const EMPTY_INFO: ShipmentInfo = { carrier: null, vehicle_no: null, driver_name: null, driver_phone: null, seal_no: null };

/** A pick list number, a sales order number or a delivery order number gives that order's delivery order */
async function startFrom(code: string): Promise<Shipment> {
  const hits = await lookupDocument(code);
  const shipHit = hits.find((h) => h.doc_type === "SHIP" && h.status === "DRAFT");
  if (shipHit) return (await fetchShipment(shipHit.id, shipHit.doc_no)).data;
  const orderId = hits.find((h) => h.doc_type === "SO")?.id ?? hits.find((h) => h.doc_type === "PICK")?.ref_document_id;
  if (orderId) return shipmentForOrder(orderId);
  throw new Error(`${code} is not a pick list, sales order or delivery order being loaded`);
}

/**
 * Loading a delivery order: scan the pick list or sales order number -> scan every piece as it goes onto the vehicle
 * (a carton barcode counts its pack size; wrong items and extra pieces are refused) -> choose the vehicle and driver
 * from recent ones, scan the seal -> post. The delivery order cannot be posted before every piece is scanned.
 */
export default function ShipScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const params = useLocalSearchParams<{ doc?: string }>();
  const findItem = useMasterData((st) => st.findItem);
  const baseFactor = useMasterData((st) => st.baseFactor);
  const submitOp = useQueue((st) => st.submit);

  const [loading, setLoading] = useState<DocumentSummary[] | null>(null);
  const [ship, setShip] = useState<Shipment | null>(null);
  // Scanned quantities per line on this device (sent to the server after every scan)
  const [checked, setChecked] = useState<Record<string, number>>({});
  const [info, setInfo] = useState<ShipmentInfo>(EMPTY_INFO);
  const [history, setHistory] = useState<LoadingHistory | null>(null);
  const [showLines, setShowLines] = useState(true);
  const [notice, setNotice] = useNotice();
  const [busy, setBusy] = useState(true);

  const loadList = async () => {
    setBusy(true);
    try {
      const { data, cachedAt } = await fetchLoadingShipments();
      setLoading(data);
      if (cachedAt) setNotice({ kind: "warning", text: "Offline: showing the cached list" }, { silent: true });
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const open = (data: Shipment) => {
    setShip(data);
    setChecked(Object.fromEntries(data.lines.map((l) => [l.id, l.qty_checked])));
    setInfo({ ...EMPTY_INFO, ...data.shipment_info, seal_no: data.shipment_info?.seal_no ?? null });
    setNotice(null);
    fetchLoadingHistory().then((h) => setHistory(h.data), () => undefined);
  };

  const openSummary = async (summary: DocumentSummary) => {
    setBusy(true);
    try {
      open((await fetchShipment(summary.id, summary.doc_no)).data);
    } catch (error) {
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const scanStart = async (code: string) => {
    setBusy(true);
    await startFrom(code).then(open, (error: unknown) => setNotice({ kind: "error", text: errorText(error) }));
    setBusy(false);
  };

  useEffect(() => {
    // State is set from the promise callbacks only (busy starts true)
    const first = params.doc ? startFrom(params.doc).then(open) : Promise.resolve();
    first
      .catch((error: unknown) => setNotice({ kind: "error", text: errorText(error) }))
      .then(fetchLoadingShipments)
      .then(({ data }) => setLoading(data), () => setLoading([]))
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on mount
  }, []);

  const left = (l: ShipmentLine) => l.qty_actual - (checked[l.id] ?? 0);
  const total = ship ? ship.lines.reduce((sum, l) => sum + l.qty_actual, 0) : 0;
  const done = ship ? ship.lines.reduce((sum, l) => sum + (checked[l.id] ?? 0), 0) : 0;
  const complete = !!ship && ship.lines.every((l) => left(l) <= 0);

  const scanPiece = (code: string) => {
    if (!ship) return;
    const match = findItem(code);
    if (!match) return setNotice({ kind: "error", text: `Unknown barcode ${code}` });
    const lines = ship.lines.filter((l) => l.item.id === match.item.id);
    if (!lines.length) return setNotice({ kind: "error", text: `${match.item.sku_code} is not on this delivery order. Take it off the vehicle.` });
    const pieces = baseFactor(match.item, match.uomId);
    if (pieces === null) return setNotice({ kind: "error", text: `No conversion from this barcode's unit to ${match.item.sku_code}'s base unit` });
    const line = lines.find((l) => left(l) >= pieces);
    if (!line) {
      const remaining = lines.reduce((sum, l) => sum + Math.max(left(l), 0), 0);
      return setNotice({
        kind: "error",
        text: remaining > 0
          ? `Too many: only ${fmtQty(remaining)} ${lines[0].uom.code} of ${match.item.sku_code} left, this barcode is ${fmtQty(pieces)}`
          : `All ${match.item.sku_code} is already loaded. Take this one off the vehicle.`,
      });
    }
    const qty = (checked[line.id] ?? 0) + pieces;
    setChecked((m) => ({ ...m, [line.id]: qty }));
    haptic("tick");
    setNotice(
      { kind: "success", text: `${line.item.sku_code} ${fmtQty(qty)} / ${fmtQty(line.qty_actual)}${pieces > 1 ? ` (+${fmtQty(pieces)})` : ""}` },
      { silent: true },
    );
    // Not awaited: the next piece can be scanned while this one is sent ("set" semantics, sent in order)
    void submitOp("ship_check", `Load ${ship.doc_no} ${line.item.sku_code} ${fmtQty(qty)}`, { ship_id: ship.id, line_id: line.id, qty }).then(
      (outcome) => {
        if (outcome.status === "failed") setNotice({ kind: "error", text: `Scan not recorded: ${outcome.error}` });
      },
    );
  };

  const finish = async () => {
    if (!ship) return;
    setBusy(true);
    const infoOutcome = await submitOp("ship_info", `Loading details ${ship.doc_no}`, { ship_id: ship.id, info });
    if (infoOutcome.status === "failed") {
      setBusy(false);
      return setNotice({ kind: "error", text: `Loading details rejected: ${infoOutcome.error}` });
    }
    const outcome = await submitOp("ship_post", `Post delivery ${ship.doc_no}`, { ship_id: ship.id });
    setBusy(false);
    if (outcome.status === "failed") {
      if (/permission/i.test(outcome.error)) {
        setNotice({ kind: "info", text: `Everything is loaded. Ask a supervisor to post ${ship.doc_no} and print the delivery order.` });
        return;
      }
      return setNotice({ kind: "error", text: `Posting rejected: ${outcome.error}` });
    }
    setShip(null);
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `Delivery order ${outcome.docNo} posted; print it in the web console for the driver` }
        : { kind: "warning", text: `Saved on this device; it will be posted when back online (${outcome.reason})` },
    );
    void loadList();
  };

  if (!ship) {
    return (
      <Screen
        notice={notice}
        onDismiss={() => setNotice(null)}
        refreshControl={<RefreshControl refreshing={busy && loading !== null} onRefresh={() => void loadList()} colors={[c.primary]} tintColor={c.primary} />}
      >
        <ScanInput
          label="Scan the pick list or sales order"
          icon="file-document-outline"
          onScan={(code) => void scanStart(code)}
          active={!busy}
          testID="scan-order"
        />
        {loading && loading.length > 0 && (
          <>
            <Text style={s.listHeader}>Or continue loading</Text>
            {loading.map((x) => (
              <ListRow key={x.id} icon="truck-outline" title={x.doc_no} subtitle={x.remark || undefined} onPress={() => void openSummary(x)} disabled={busy} testID={`ship-${x.doc_no}`} />
            ))}
          </>
        )}
        {loading && loading.length === 0 && (
          <EmptyState icon="truck-check-outline" title="No delivery orders being loaded" text="Scan the number on the pick list to start loading its order." />
        )}
      </Screen>
    );
  }

  const field = (key: keyof ShipmentInfo, label: string, testID: string) => (
    <Field label={label} value={info[key] ?? ""} onChangeText={(v) => setInfo((i) => ({ ...i, [key]: v || null }))} testID={testID} />
  );

  return (
    <Screen
      notice={notice}
      onDismiss={() => setNotice(null)}
      steps={["Scan pieces", "Vehicle", "Post"]}
      step={complete ? 1 : 0}
      footer={
        complete ? (
          <Button title="Post delivery order" icon="truck-check" onPress={() => void finish()} loading={busy} testID="post-delivery" />
        ) : undefined
      }
    >
      <View style={s.progressHead}>
        <View style={{ flex: 1 }}>
          <Text style={s.docNo}>{ship.doc_no}</Text>
          <Text style={s.muted} numberOfLines={1}>
            {ship.partner?.name ?? ""}
            {ship.ref_document ? ` · ${ship.ref_document.doc_no}` : ""}
          </Text>
        </View>
        <Text style={s.progressText} testID="loaded-count">
          {fmtQty(done)}
          <Text style={s.muted}>{` / ${fmtQty(total)}`}</Text>
        </Text>
      </View>
      <ProgressBar value={total ? done / total : 0} tone={complete ? "success" : "primary"} />

      {!complete && <ScanInput label="Scan every piece going onto the vehicle" onScan={scanPiece} active={!busy} testID="scan-piece" />}

      {complete && (
        <Card>
          <Text style={s.sectionTitle}>Vehicle and driver</Text>
          {history && history.vehicles.length > 0 && (
            <View style={s.chips}>
              {history.vehicles.slice(0, 8).map((v, i) => {
                const chosen = v.vehicle_no === info.vehicle_no && v.driver_name === info.driver_name;
                return (
                  <Pressable
                    key={i}
                    accessibilityRole="button"
                    onPress={() => setInfo((cur) => ({ ...cur, carrier: v.carrier, vehicle_no: v.vehicle_no, driver_name: v.driver_name, driver_phone: v.driver_phone }))}
                    style={[s.chip, chosen && s.chipChosen]}
                    testID={`vehicle-${i}`}
                  >
                    <Text style={[s.chipText, chosen && { color: c.primaryText }]}>{[v.vehicle_no, v.driver_name].filter(Boolean).join(" · ")}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}
          {field("vehicle_no", "Vehicle no.", "vehicle-no")}
          {field("driver_name", "Driver", "driver-name")}
          {field("driver_phone", "Driver phone", "driver-phone")}
          {field("carrier", "Carrier", "carrier")}
          {field("seal_no", "Seal no. (scannable)", "seal-no")}
        </Card>
      )}

      <Card>
        <Pressable accessibilityRole="button" onPress={() => setShowLines((v) => !v)} style={s.linesToggle}>
          <Text style={s.sectionTitle}>Lines ({ship.lines.length})</Text>
          <MaterialCommunityIcons name={showLines ? "chevron-up" : "chevron-down"} size={24} color={c.textMuted} />
        </Pressable>
        {showLines &&
          ship.lines.map((l, i) => {
            const qty = checked[l.id] ?? 0;
            const full = qty >= l.qty_actual;
            return (
              <View key={l.id}>
                {i > 0 && <Divider />}
                <View style={s.lineRow}>
                  <MaterialCommunityIcons name={full ? "check-circle" : "circle-outline"} size={20} color={full ? c.successText : c.textMuted} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.lineText} numberOfLines={1}>
                      <Text style={{ fontWeight: "700" }}>{l.item.sku_code}</Text> {l.item.name}
                    </Text>
                    {(l.batch_no || l.expiry_date) && (
                      <View style={{ flexDirection: "row", gap: space.xs, marginTop: 2 }}>
                        {l.batch_no && <Pill tone="info" text={`Batch ${l.batch_no}`} />}
                        {l.expiry_date && <Pill tone="warning" text={`Exp ${l.expiry_date}`} />}
                      </View>
                    )}
                  </View>
                  <Text style={[s.lineQty, { color: full ? c.successText : c.textMuted }]}>
                    {`${fmtQty(qty)} / ${fmtQty(l.qty_actual)} ${l.uom.code}`}
                  </Text>
                </View>
              </View>
            );
          })}
      </Card>

      <Button title="Change delivery order" variant="ghost" icon="swap-horizontal" onPress={() => { setShip(null); void loadList(); }} />
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    listHeader: { fontSize: 13, fontWeight: "600", color: c.textSecondary, textTransform: "uppercase", letterSpacing: 0.6 },
    progressHead: { flexDirection: "row", alignItems: "flex-end", gap: space.md },
    docNo: { fontSize: 17, fontWeight: "700", color: c.text },
    muted: { fontSize: 13, color: c.textMuted, fontWeight: "400" },
    progressText: { fontSize: 28, fontWeight: "800", color: c.text, fontVariant: ["tabular-nums"] },
    sectionTitle: { fontSize: 16, fontWeight: "600", color: c.text },
    chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginVertical: space.sm },
    chip: { borderWidth: 1, borderColor: c.border, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: space.sm, minHeight: 44, justifyContent: "center" },
    chipChosen: { borderColor: c.primary, backgroundColor: c.primaryTint },
    chipText: { fontSize: 14, fontWeight: "600", color: c.text },
    linesToggle: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 32 },
    lineRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 10, paddingHorizontal: 4 },
    lineText: { fontSize: 14, color: c.text },
    lineQty: { fontSize: 13, fontWeight: "600", fontVariant: ["tabular-nums"] },
  });
