import { useEffect, useState } from "react";

import { useLocalSearchParams } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import ScanInput from "@/components/ScanInput";
import Screen from "@/components/Screen";
import { Card, Divider, EmptyState, Pill } from "@/components/ui";
import { errorText } from "@/lib/api";
import { useNotice } from "@/lib/feedback";
import { fetchBalances, fetchItemBalances, fmtQty } from "@/lib/inbound";
import type { StockBalance } from "@/lib/types";
import { useMasterData } from "@/stores/masterData";
import { space, useStyles, type Palette } from "@/theme";

type Subject = { kind: "location" | "item"; id: string; title: string; subtitle: string };

/** What is in a bin, or where an item is: scan a bin or an item (also opened from the home screen's scan field) */
export default function StockScreen() {
  const s = useStyles(makeStyles);
  const params = useLocalSearchParams<{ code?: string }>();
  const findItem = useMasterData((st) => st.findItem);
  const findLocation = useMasterData((st) => st.findLocation);
  const subjectFor = (code: string): Subject | null => {
    const location = findLocation(code);
    if (location) return { kind: "location", id: location.id, title: location.code, subtitle: location.name };
    const match = findItem(code);
    return match ? { kind: "item", id: match.item.id, title: match.item.sku_code, subtitle: match.item.name } : null;
  };
  // Opened from the home screen's scan field: the scanned bin or item is known at once
  const [subject, setSubject] = useState<Subject | null>(() => (params.code ? subjectFor(params.code) : null));
  const [rows, setRows] = useState<StockBalance[] | null>(null);
  const [notice, setNotice] = useNotice();
  const [busy, setBusy] = useState(false);

  const load = (next: Subject) =>
    (next.kind === "location" ? fetchBalances(next.id, next.title) : fetchItemBalances(next.id, next.title)).then(
      ({ data, cachedAt }) => {
        setRows(data.filter((r) => r.qty_on_hand !== 0));
        setNotice(cachedAt ? { kind: "warning", text: `Offline: stock as of ${cachedAt.slice(0, 16).replace("T", " ")}` } : null, { silent: true });
      },
      (error: unknown) => setNotice({ kind: "error", text: errorText(error) }),
    );

  const show = async (code: string) => {
    const next = subjectFor(code);
    if (!next) return setNotice({ kind: "error", text: `${code} is not a known bin or item` });
    setSubject(next);
    setRows(null);
    setBusy(true);
    await load(next);
    setBusy(false);
  };

  useEffect(() => {
    if (subject) void load(subject);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once on mount, for the subject opened with
  }, []);

  const total = rows?.reduce((sum, r) => sum + r.qty_on_hand, 0) ?? 0;

  return (
    <Screen notice={notice} onDismiss={() => setNotice(null)}>
      <ScanInput label="Scan a bin or an item" onScan={(code) => void show(code)} active={!busy} testID="scan-stock" />
      {subject && (
        <Card>
          <Text style={s.title} testID="stock-subject">{subject.title}</Text>
          <Text style={s.muted}>{subject.subtitle}</Text>
          {rows === null ? (
            <Text style={s.muted}>Loading…</Text>
          ) : rows.length === 0 ? (
            <EmptyState icon="package-variant" title={subject.kind === "location" ? "Empty bin" : "Not in stock"} />
          ) : (
            rows.map((r, i) => (
              <View key={r.id}>
                {i > 0 && <Divider />}
                <View style={s.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.rowTitle}>{subject.kind === "location" ? r.item.sku_code : r.location.code}</Text>
                    <Text style={s.muted} numberOfLines={1}>{subject.kind === "location" ? r.item.name : r.location.name}</Text>
                    {(r.batch_no || r.expiry_date) && (
                      <View style={{ flexDirection: "row", gap: space.xs, marginTop: 2 }}>
                        {r.batch_no && <Pill tone="info" text={`Batch ${r.batch_no}`} />}
                        {r.expiry_date && <Pill tone="warning" text={`Exp ${r.expiry_date}`} />}
                      </View>
                    )}
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={s.qty}>{fmtQty(r.qty_on_hand)} {r.item.base_uom.code}</Text>
                    {r.qty_allocated > 0 && <Text style={s.muted}>{fmtQty(r.qty_allocated)} allocated</Text>}
                  </View>
                </View>
              </View>
            ))
          )}
          {subject.kind === "item" && rows && rows.length > 1 && (
            <Text style={[s.muted, { textAlign: "right", marginTop: space.sm }]}>Total {fmtQty(total)}</Text>
          )}
        </Card>
      )}
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    title: { fontSize: 22, fontWeight: "800", color: c.text },
    muted: { fontSize: 13, color: c.textMuted },
    row: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: 10 },
    rowTitle: { fontSize: 15, fontWeight: "700", color: c.text },
    qty: { fontSize: 18, fontWeight: "800", color: c.text, fontVariant: ["tabular-nums"] },
  });
