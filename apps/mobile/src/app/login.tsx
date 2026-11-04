import { useState } from "react";

import { useRouter } from "expo-router";
import { ScrollView, Text } from "react-native";

import { Banner, Button, Card, Field, styles, type Notice } from "@/components/ui";
import { ApiError, errorText, request } from "@/lib/api";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";

export default function LoginScreen() {
  const router = useRouter();
  const session = useSession();
  const [serverUrl, setServerUrl] = useState(session.serverUrl);
  const [username, setUsername] = useState(session.username ?? "");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const login = async () => {
    setLoading(true);
    setNotice(null);
    session.setServerUrl(serverUrl);
    try {
      const { access_token } = await request<{ access_token: string }>(
        "POST",
        "/auth/login",
        { username: username.trim(), password },
        { form: true },
      );
      session.setLogin(access_token, username.trim());
      useQueue.setState({ needsLogin: false });
      // A failed master data download does not block sign-in: the home screen asks for a manual update when there is none
      await useMasterData
        .getState()
        .refresh()
        .catch(() => undefined);
      void useQueue.getState().sync();
      router.replace("/");
    } catch (error) {
      const text =
        error instanceof ApiError && error.kind === "network"
          ? "Cannot reach the server; check the server URL and network"
          : errorText(error);
      setNotice({ kind: "error", text });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      <Banner notice={notice} />
      <Card>
        <Field label="Server URL" value={serverUrl} onChangeText={setServerUrl} testID="server-url" />
        <Text style={styles.hint}>e.g. http://192.168.1.10:8000/api/v1 (ask your system administrator)</Text>
      </Card>
      <Card>
        <Field label="Username" value={username} onChangeText={setUsername} testID="username" />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          testID="password"
          onSubmitEditing={login}
        />
        <Button title="Sign in" onPress={login} loading={loading} disabled={!username || !password} testID="login" />
      </Card>
    </ScrollView>
  );
}
