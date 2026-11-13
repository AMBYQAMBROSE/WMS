import { useState } from "react";

import { StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen, { ContextBar } from "@/components/Screen";
import { Card, Divider, Pill } from "@/components/ui";
import { errorText } from "@/lib/api";
import { haptic, useNotice } from "@/lib/feedback";
import { fetchBalances, fmtQty } from "@/lib/inbound";
import type { MobileLocation, StockBalance } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { space, useStyles, useTheme, type Palette } from "@/theme";

const TARGET_TYPES = ["BIN", "DOCK"];

/** Stock on a balance that is free to move; allocated stock stays behind for its order */
const movable = (b: StockBalance) => Math.max(b.qty_on_hand - b.qty_allocated, 0);

/**
 * Location move: scan location A (its stock loads automatically) -> scan location B -> everything movable at A
 * is moved to B in one document. The two scans are the only inputs on the screen.
 */
export default function LocationMoveScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const findLocation = useMasterData((st) => st.findLocation);
  const findAfterUpdate = useMasterData((st) => st.findAfterUpdate);
  const submitOp = useQueue((st) => st.submit);

  const [from, setFrom] = useState<MobileLocation | null>(null);
  const [balances, setBalances] = useState<StockBalance[]>([]);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [notice, setNotice] = useNotice();
  const [busy, setBusy] = useState(false);

  const lines = balances.filter((b) => movable(b) > 0);
  const allocated = balances.reduce((sum, b) => sum + b.qty_allocated, 0);

  const reset = () => {
    setFrom(null);
    setBalances([]);
    setCachedAt(null);
  };

  const scanFrom = async (code: string) => {
    const loc = findLocation(code) ?? (await findAfterUpdate(() => findLocation(code)));
    if (!loc) return setNotice({ kind: "error", text: `Location ${code} not found (for new locations, update master data on the home screen first)` });
    if (loc.is_locked) return setNotice({ kind: "error", text: `Location ${loc.code} is locked` });
    setBusy(true);
    try {
      const { data, cachedAt: cached } = await fetchBalances(loc.id, loc.code);
      if (!data.some((b) => movable(b) > 0)) {
        return setNotice({
          kind: "error",
          text: data.length ? `All stock at ${loc.code} is allocated to orders; nothing to move` : `Location ${loc.code} has no stock`,
        });
      }
      setFrom(loc);
      setBalances(data);
      setCachedAt(cached ?? null);
      if (cached) {
        setNotice({ kind: "warning", text: `Offline: using stock cached at ${new Date(cached).toLocaleString()}; the server decides on submit` });
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

  const scanTo = async (code: string) => {
    if (!from) return;
    const to = findLocation(code) ?? (await findAfterUpdate(() => findLocation(code)));
    if (!to) return setNotice({ kind: "error", text: `Location ${code} not found` });
    if (!TARGET_TYPES.includes(to.location_type)) return setNotice({ kind: "error", text: `${to.code} is not a bin or dock location` });
    if (to.is_locked) return setNotice({ kind: "error", text: `Target location ${to.code} is locked` });
    if (to.id === from.id) return setNotice({ kind: "error", text: "Location B cannot be the same as location A" });

    setBusy(true);
    const outcome = await submitOp(
      "move",
      `Move ${from.code} → ${to.code}`,
      {
        lines: lines.map((b) => ({
          item_id: b.item.id,
          uom_id: b.item.base_uom.id,
          qty: movable(b),
          batch_no: b.batch_no,
          expiry_date: b.expiry_date,
          from_location_id: from.id,
          to_location_id: to.id,
        })),
      },
      lines.map((b) => `${b.item.sku_code} × ${fmtQty(movable(b))} → ${to.code}${b.batch_no ? ` batch ${b.batch_no}` : ""}`),
    );
    setBusy(false);
    if (outcome.status === "failed") return setNotice({ kind: "error", text: `Rejected: ${outcome.error}` });

    const left = allocated > 0 ? `; ${fmtQty(allocated)} allocated stayed at ${from.code}` : "";
    setNotice(
      outcome.status === "done"
        ? { kind: "success", text: `${from.code} → ${to.code} moved (${lines.length} lines), document no. ${outcome.docNo}${left}` }
        : { kind: "warning", text: `Saved on this device; it will be submitted when back online (${outcome.reason})` },
    );
    reset();
  };

  return (
    <Screen notice={notice} onDismiss={() => setNotice(null)} steps={["Location A", "Location B"]} step={from ? 1 : 0}>
      {!from ? (
        <ScanInput label="Scan location A (move from)" icon="map-marker-radius" onScan={(code) => void scanFrom(code)} active={!busy} testID="scan-from" />
      ) : (
        <>
          <ContextBar
            items={[{ icon: "map-marker-radius", label: "Location A", value: from.code, sub: from.name }]}
            onChange={reset}
            badge={
              <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
                <Pill icon="package-variant-closed" text={`${lines.length} line${lines.length === 1 ? "" : "s"} to move`} />
                {allocated > 0 && <Pill tone="warning" icon="lock-outline" text={`${fmtQty(allocated)} allocated stays`} />}
                {cachedAt && <Pill tone="warning" icon="cloud-off-outline" text={`Cached ${new Date(cachedAt).toLocaleTimeString()}`} />}
              </View>
            }
          />

          <ScanInput label="Scan location B (move to)" icon="map-marker-radius" onScan={(code) => void scanTo(code)} active={!busy} testID="scan-to" />

          <Card title={`Moving from ${from.code}`} icon="package-variant-closed">
            {lines.map((b, i) => (
              <View key={b.id}>
                {i > 0 && <Divider />}
                <View style={s.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.title} numberOfLines={1}>
                      {b.item.sku_code} <Text style={{ fontWeight: "400", color: c.textSecondary }}>{b.item.name}</Text>
                    </Text>
                    {(b.batch_no || b.expiry_date) && (
                      <Text style={s.sub}>
                        {[b.batch_no && `Batch ${b.batch_no}`, b.expiry_date && `Exp ${b.expiry_date}`].filter(Boolean).join("  ·  ")}
                      </Text>
                    )}
                  </View>
                  <Text style={s.qty}>
                    {fmtQty(movable(b))} {b.item.base_uom.code}
                  </Text>
                </View>
              </View>
            ))}
          </Card>
        </>
      )}
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    row: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: 6 },
    title: { fontSize: 16, fontWeight: "600", color: c.text },
    sub: { fontSize: 13, color: c.textMuted },
    qty: { fontSize: 16, fontWeight: "700", color: c.text, fontVariant: ["tabular-nums"] },
  });
