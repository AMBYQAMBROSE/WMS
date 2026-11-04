import { useRouter } from "expo-router";
import { Pressable, Text } from "react-native";

import { colors } from "@/components/ui";
import { useQueue } from "@/stores/queue";

export default function SyncIndicator() {
  const router = useRouter();
  const pending = useQueue((s) => s.ops.filter((o) => o.status === "pending").length);
  const failed = useQueue((s) => s.ops.filter((o) => o.status === "failed").length);
  const online = useQueue((s) => s.online);
  const syncing = useQueue((s) => s.syncing);

  const dot = online === false ? colors.danger : colors.success;
  const label = syncing ? "Syncing" : online === false ? "Offline" : "Online";
  return (
    <Pressable testID="sync-indicator" onPress={() => router.push("/queue")} style={{ paddingHorizontal: 8 }}>
      <Text style={{ fontSize: 13, color: colors.text }}>
        <Text style={{ color: dot }}>● </Text>
        {label}
        {pending > 0 && ` · Pending ${pending}`}
        {failed > 0 && <Text style={{ color: colors.danger }}>{` · Failed ${failed}`}</Text>}
      </Text>
    </Pressable>
  );
}
