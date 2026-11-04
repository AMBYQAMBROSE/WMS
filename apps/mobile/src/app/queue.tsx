import { ScrollView, Text, View } from "react-native";

import { Banner, Button, Card, Row, colors, styles } from "@/components/ui";
import { useQueue } from "@/stores/queue";

export default function QueueScreen() {
  const { ops, completed, syncing, online, lastError, sync, remove } = useQueue();
  const pending = ops.filter((o) => o.status === "pending");
  const failed = ops.filter((o) => o.status === "failed");

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      {online === false && lastError && <Banner notice={{ kind: "warning", text: `Offline: ${lastError}` }} />}
      <Button title="Sync now" onPress={() => void sync()} loading={syncing} disabled={!pending.length} testID="sync-now" />

      <Card>
        <Text style={styles.title}>Pending ({pending.length})</Text>
        {pending.length === 0 && <Text style={styles.hint}>Nothing pending</Text>}
        {pending.map((op) => (
          <Row key={op.id} label={op.title} value={new Date(op.createdAt).toLocaleTimeString()} />
        ))}
      </Card>

      {failed.length > 0 && (
        <Card>
          <Text style={[styles.title, { color: colors.danger }]}>Failed ({failed.length})</Text>
          <Text style={styles.hint}>
            The server rejected these records under business rules (e.g. over-receipt, insufficient stock); retrying will not help. Check the goods, redo the work, then delete the records here.
          </Text>
          {failed.map((op) => (
            <View key={op.id} style={{ gap: 4, paddingVertical: 6, borderTopWidth: 1, borderColor: colors.border }}>
              <Row label={op.title} value={new Date(op.createdAt).toLocaleString()} />
              <Text style={{ color: colors.danger }}>{op.error}</Text>
              <Button title="Delete" variant="danger" onPress={() => remove(op.id)} />
            </View>
          ))}
        </Card>
      )}

      <Card>
        <Text style={styles.title}>Recently completed</Text>
        {completed.length === 0 && <Text style={styles.hint}>None</Text>}
        {completed.map((c) => (
          <Row key={c.id} label={`${c.title} → ${c.docNo}`} value={new Date(c.completedAt).toLocaleTimeString()} />
        ))}
      </Card>
    </ScrollView>
  );
}
