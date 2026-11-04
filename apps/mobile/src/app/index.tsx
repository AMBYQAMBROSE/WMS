import { useState } from "react";

import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text } from "react-native";

import { Banner, Button, Card, Row, styles, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";

export default function HomeScreen() {
  const router = useRouter();
  const { token, username, serverUrl, logout } = useSession();
  const data = useMasterData((s) => s.data);
  const needsLogin = useQueue((s) => s.needsLogin);
  const pending = useQueue((s) => s.ops.length);
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  if (!token) return <Redirect href="/login" />;

  const refresh = async () => {
    setRefreshing(true);
    try {
      await useMasterData.getState().refresh();
      setNotice({ kind: "success", text: "Master data updated" });
    } catch (error) {
      setNotice({ kind: "error", text: `Update failed: ${errorText(error)}` });
    } finally {
      setRefreshing(false);
    }
  };

  const doLogout = () => {
    logout();
    router.replace("/login");
  };

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      {needsLogin && (
        <Banner notice={{ kind: "warning", text: `Session expired; ${pending} record(s) waiting to submit. Sign in again to continue automatically` }} />
      )}
      {!data && <Banner notice={{ kind: "warning", text: "No master data yet, so barcodes cannot be recognized. Update master data first" }} />}
      <Banner notice={notice} />

      <Button title="Receive" onPress={() => router.push("/receive")} disabled={!data} testID="menu-receive" />
      <Button title="Put away" onPress={() => router.push("/putaway")} disabled={!data} testID="menu-putaway" />
      <Button title="Move" onPress={() => router.push("/move")} disabled={!data} testID="menu-move" />
      <Button title="Count" onPress={() => router.push("/count")} disabled={!data} testID="menu-count" />
      <Button title="Pick" onPress={() => router.push("/pick")} disabled={!data} testID="menu-pick" />
      <Button title={`Submit queue${pending ? ` (${pending})` : ""}`} variant="default" onPress={() => router.push("/queue")} />

      <Card>
        <Text style={styles.title}>Master data</Text>
        {data ? (
          <>
            <Row label="Items" value={`${data.items.length}`} />
            <Row label="Locations" value={`${data.locations.length}`} />
            <Row label="Updated" value={new Date(data.generated_at + "Z").toLocaleString()} />
          </>
        ) : (
          <Text style={styles.hint}>Not downloaded</Text>
        )}
        <Button title="Update master data" variant="default" onPress={refresh} loading={refreshing} testID="refresh-master" />
      </Card>

      <Card>
        <Row label="User" value={username ?? ""} />
        <Row label="Server" value={serverUrl} />
        <Button title={needsLogin ? "Sign in again" : "Sign out"} variant="danger" onPress={doLogout} />
      </Card>
    </ScrollView>
  );
}
