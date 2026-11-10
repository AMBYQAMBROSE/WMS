import { useRouter } from "expo-router";
import { Pressable, Text } from "react-native";

import { isMine, useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { useTheme } from "@/theme";

export default function SyncIndicator() {
  const { c } = useTheme();
  const router = useRouter();
  const username = useSession((s) => s.username);
  const pending = useQueue((s) => s.ops.filter((o) => o.status === "pending" && isMine(o, username)).length);
  // Recorded by someone else on this PDA: waits for them to sign in
  const held = useQueue((s) => s.ops.filter((o) => o.status === "pending" && !isMine(o, username)).length);
  const failed = useQueue((s) => s.ops.filter((o) => o.status === "failed").length);
  const online = useQueue((s) => s.online);
  const syncing = useQueue((s) => s.syncing);

  const offline = online === false;
  const dot = failed > 0 || offline ? c.danger : pending > 0 ? c.warning : c.success;
  // online stays null until the queue has sent something: nothing is known to be wrong, so "Ready"
  const label = syncing ? "Syncing" : offline ? "Offline" : online === null ? "Ready" : "Online";
  return (
    <Pressable
      testID="sync-indicator"
      accessibilityRole="button"
      accessibilityHint="Opens the submit queue"
      onPress={() => router.push("/queue")}
      hitSlop={8}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 999,
        backgroundColor: pressed ? c.border : c.surfaceAlt,
        borderWidth: 1,
        borderColor: c.border,
        marginRight: 4,
      })}
    >
      <Text style={{ fontSize: 13, fontWeight: "600", color: c.textSecondary, fontVariant: ["tabular-nums"] }}>
        <Text style={{ color: dot }}>● </Text>
        {label}
        {pending > 0 && <Text style={{ color: c.warningText }}>{` · Pending ${pending}`}</Text>}
        {held > 0 && ` · Others' ${held}`}
        {failed > 0 && <Text style={{ color: c.dangerText }}>{` · Failed ${failed}`}</Text>}
      </Text>
    </Pressable>
  );
}
