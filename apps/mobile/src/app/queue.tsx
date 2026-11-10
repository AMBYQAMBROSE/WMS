import { MaterialCommunityIcons } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";

import Screen from "@/components/Screen";
import { Banner, Button, Card, Divider, EmptyState, SectionHeader } from "@/components/ui";
import { confirm } from "@/lib/feedback";
import { isMine, useQueue, type QueuedOp } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

function Details({ op }: { op: QueuedOp }) {
  const s = useStyles(makeStyles);
  if (!op.details?.length) return null;
  return (
    <View style={s.details}>
      {op.details.map((line, i) => (
        <Text key={i} style={s.detailLine}>
          {line}
        </Text>
      ))}
    </View>
  );
}

function OpHead({ op, meta }: { op: QueuedOp; meta: string }) {
  const s = useStyles(makeStyles);
  return (
    <View style={s.opHead}>
      <Text style={s.opTitle}>{op.title}</Text>
      <Text style={s.opMeta}>{meta}</Text>
    </View>
  );
}

export default function QueueScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const ops = useQueue((st) => st.ops);
  const completed = useQueue((st) => st.completed);
  const syncing = useQueue((st) => st.syncing);
  const online = useQueue((st) => st.online);
  const lastError = useQueue((st) => st.lastError);
  const sync = useQueue((st) => st.sync);
  const retry = useQueue((st) => st.retry);
  const remove = useQueue((st) => st.remove);
  const username = useSession((st) => st.username);
  const mine = ops.filter((o) => isMine(o, username));
  const pending = mine.filter((o) => o.status === "pending");
  const failed = ops.filter((o) => o.status === "failed");
  const others = ops.filter((o) => o.status === "pending" && !isMine(o, username));
  const otherUsers = [...new Set(others.map((o) => o.createdBy))];

  const askDelete = (op: QueuedOp) =>
    confirm("Delete this record?", `"${op.title}" will never be submitted. Only do this if the work was redone another way.`, "Delete", () =>
      remove(op.id),
    );

  const statusIcon = online === false ? "cloud-off-outline" : syncing ? "cloud-sync-outline" : pending.length ? "cloud-upload-outline" : "cloud-check-outline";
  const statusColor = online === false ? c.dangerText : pending.length ? c.warningText : c.successText;
  const statusText =
    online === false ? "Offline" : syncing ? "Syncing…" : pending.length ? `${pending.length} waiting to submit` : "Everything is submitted";

  return (
    <Screen
      footer={
        <Button title="Sync now" icon="sync" onPress={() => void sync()} loading={syncing} disabled={!pending.length} testID="sync-now" />
      }
    >
      <View style={s.status}>
        <MaterialCommunityIcons name={statusIcon} size={32} color={statusColor} />
        <View style={{ flex: 1 }}>
          <Text style={[s.statusText, { color: statusColor }]}>{statusText}</Text>
          <Text style={s.statusSub}>Records sync by themselves every 20 s and when the app opens</Text>
        </View>
      </View>

      {online === false && lastError && <Banner notice={{ kind: "warning", text: `Offline: ${lastError}` }} />}

      {failed.length > 0 && (
        <>
          <SectionHeader title="Failed" count={failed.length} />
          <Card testID="failed-ops" style={{ borderColor: c.danger, borderWidth: 1 }}>
            <Text style={s.hint}>
              The server rejected these under business rules (e.g. over-receipt, insufficient stock). Fix the cause, then
              retry; or delete the record if the work was redone another way.
            </Text>
            {failed.map((op) => (
              <View key={op.id} style={s.op}>
                <Divider />
                <OpHead op={op} meta={`${op.createdBy ?? ""} · ${new Date(op.createdAt).toLocaleString()}`} />
                <Details op={op} />
                <View style={s.error}>
                  <MaterialCommunityIcons name="alert-circle" size={18} color={c.dangerText} />
                  <Text style={s.errorText}>{op.error}</Text>
                </View>
                <View style={{ flexDirection: "row", gap: space.sm }}>
                  <Button title="Delete" variant="danger" icon="trash-can-outline" compact onPress={() => askDelete(op)} style={{ flex: 1 }} />
                  {isMine(op, username) && (
                    <Button title="Retry" icon="refresh" compact onPress={() => void retry(op.id)} loading={syncing} testID="retry-op" style={{ flex: 1 }} />
                  )}
                </View>
              </View>
            ))}
          </Card>
        </>
      )}

      <SectionHeader title="Pending" count={pending.length} />
      <Card>
        {pending.length === 0 && <Text style={s.hint}>Nothing pending</Text>}
        {pending.map((op, i) => (
          <View key={op.id} style={s.op}>
            {i > 0 && <Divider />}
            <OpHead op={op} meta={new Date(op.createdAt).toLocaleTimeString()} />
            <Details op={op} />
          </View>
        ))}
      </Card>

      {others.length > 0 && (
        <>
          <SectionHeader title="Waiting for another user" count={others.length} />
          <Card testID="held-for-others">
            <Text style={s.hint}>
              Recorded on this PDA by {otherUsers.join(", ")}. They are submitted when that person signs in here again, so the
              work is recorded under the person who did it. Delete them only if the work was redone another way.
            </Text>
            {others.map((op) => (
              <View key={op.id} style={s.op}>
                <Divider />
                <OpHead op={op} meta={`${op.createdBy} · ${new Date(op.createdAt).toLocaleString()}`} />
                <Details op={op} />
                <Button title="Delete" variant="danger" icon="trash-can-outline" compact onPress={() => askDelete(op)} />
              </View>
            ))}
          </Card>
        </>
      )}

      <SectionHeader title="Recently completed" count={completed.length} />
      {completed.length === 0 ? (
        <Card>
          <EmptyState icon="cloud-check-outline" title="Nothing completed yet" />
        </Card>
      ) : (
        <Card>
          {completed.map((cp, i) => (
            <View key={cp.id} style={s.op}>
              {i > 0 && <Divider />}
              <View style={s.done}>
                <MaterialCommunityIcons name="check-circle" size={20} color={c.successText} />
                <Text style={s.doneText}>{`${cp.title} → ${cp.docNo}`}</Text>
                <Text style={s.opMeta}>{new Date(cp.completedAt).toLocaleTimeString()}</Text>
              </View>
              {cp.warning && <Text style={{ color: c.warningText, fontSize: 13 }}>{cp.warning}</Text>}
            </View>
          ))}
        </Card>
      )}
    </Screen>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    status: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.md,
      padding: space.lg,
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
    },
    statusText: { fontSize: 18, fontWeight: "700" },
    statusSub: { fontSize: 13, color: c.textMuted },
    hint: { fontSize: 13, color: c.textMuted, lineHeight: 18 },
    op: { gap: space.sm },
    opHead: { flexDirection: "row", justifyContent: "space-between", gap: space.sm, paddingTop: space.xs },
    opTitle: { fontSize: 15, fontWeight: "600", color: c.text, flex: 1 },
    opMeta: { fontSize: 13, color: c.textMuted, fontVariant: ["tabular-nums"], flexShrink: 1, textAlign: "right" },
    details: { paddingLeft: space.md, borderLeftWidth: 2, borderLeftColor: c.border, gap: 2 },
    detailLine: { fontSize: 13, color: c.textSecondary, fontVariant: ["tabular-nums"] },
    error: {
      flexDirection: "row",
      gap: space.sm,
      padding: space.md,
      borderRadius: radius.sm,
      backgroundColor: c.dangerTint,
      alignItems: "flex-start",
    },
    errorText: { flex: 1, color: c.dangerText, fontSize: 14, fontWeight: "500" },
    done: { flexDirection: "row", alignItems: "center", gap: space.sm },
    doneText: { flex: 1, fontSize: 14, color: c.text },
  });
