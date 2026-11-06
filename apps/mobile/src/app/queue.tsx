import { ScrollView, Text, View } from "react-native";

import { Banner, Button, Card, Row, colors, styles } from "@/components/ui";
import { isMine, useQueue, type QueuedOp } from "@/stores/queue";
import { useSession } from "@/stores/session";

function Details({ op }: { op: QueuedOp }) {
  if (!op.details?.length) return null;
  return (
    <View style={{ paddingLeft: 8, gap: 2 }}>
      {op.details.map((line, i) => (
        <Text key={i} style={styles.hint}>
          {line}
        </Text>
      ))}
    </View>
  );
}

export default function QueueScreen() {
  const { ops, completed, syncing, online, lastError, sync, retry, remove } = useQueue();
  const username = useSession((s) => s.username);
  const mine = ops.filter((o) => isMine(o, username));
  const pending = mine.filter((o) => o.status === "pending");
  const failed = ops.filter((o) => o.status === "failed");
  const others = ops.filter((o) => o.status === "pending" && !isMine(o, username));
  const otherUsers = [...new Set(others.map((o) => o.createdBy))];

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      {online === false && lastError && <Banner notice={{ kind: "warning", text: `Offline: ${lastError}` }} />}
      <Button title="Sync now" onPress={() => void sync()} loading={syncing} disabled={!pending.length} testID="sync-now" />

      <Card>
        <Text style={styles.title}>Pending ({pending.length})</Text>
        {pending.length === 0 && <Text style={styles.hint}>Nothing pending</Text>}
        {pending.map((op) => (
          <View key={op.id} style={{ paddingVertical: 4 }}>
            <Row label={op.title} value={new Date(op.createdAt).toLocaleTimeString()} />
            <Details op={op} />
          </View>
        ))}
      </Card>

      {others.length > 0 && (
        <Card testID="held-for-others">
          <Text style={styles.title}>Waiting for another user ({others.length})</Text>
          <Text style={styles.hint}>
            Recorded on this PDA by {otherUsers.join(", ")}. They are submitted when that person signs in here again, so the
            work is recorded under the person who did it. Delete them only if the work was redone another way.
          </Text>
          {others.map((op) => (
            <View key={op.id} style={{ gap: 4, paddingVertical: 6, borderTopWidth: 1, borderColor: colors.border }}>
              <Row label={op.title} value={`${op.createdBy} · ${new Date(op.createdAt).toLocaleString()}`} />
              <Details op={op} />
              <Button title="Delete" variant="danger" onPress={() => remove(op.id)} />
            </View>
          ))}
        </Card>
      )}

      {failed.length > 0 && (
        <Card testID="failed-ops">
          <Text style={[styles.title, { color: colors.danger }]}>Failed ({failed.length})</Text>
          <Text style={styles.hint}>
            The server rejected these under business rules (e.g. over-receipt, insufficient stock). Fix the cause, then
            retry; or delete the record if the work was redone another way.
          </Text>
          {failed.map((op) => (
            <View key={op.id} style={{ gap: 4, paddingVertical: 6, borderTopWidth: 1, borderColor: colors.border }}>
              <Row label={op.title} value={`${op.createdBy ?? ""} · ${new Date(op.createdAt).toLocaleString()}`} />
              <Details op={op} />
              <Text style={{ color: colors.danger }}>{op.error}</Text>
              <View style={{ flexDirection: "row", gap: 8 }}>
                {isMine(op, username) && (
                  <View style={{ flex: 1 }}>
                    <Button title="Retry" onPress={() => void retry(op.id)} loading={syncing} testID="retry-op" />
                  </View>
                )}
                <View style={{ flex: 1 }}>
                  <Button title="Delete" variant="danger" onPress={() => remove(op.id)} />
                </View>
              </View>
            </View>
          ))}
        </Card>
      )}

      <Card>
        <Text style={styles.title}>Recently completed</Text>
        {completed.length === 0 && <Text style={styles.hint}>None</Text>}
        {completed.map((c) => (
          <View key={c.id}>
            <Row label={`${c.title} → ${c.docNo}`} value={new Date(c.completedAt).toLocaleTimeString()} />
            {c.warning && <Text style={{ color: colors.warning }}>{c.warning}</Text>}
          </View>
        ))}
      </Card>
    </ScrollView>
  );
}
