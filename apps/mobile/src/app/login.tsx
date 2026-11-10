import { useRef, useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Banner, Button, Card, Field, IconButton, type Notice } from "@/components/ui";
import { ApiError, errorText, request } from "@/lib/api";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { radius, space, type, useStyles, useTheme, type Palette } from "@/theme";

export default function LoginScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const router = useRouter();
  const session = useSession();
  const [serverUrl, setServerUrl] = useState(session.serverUrl);
  const [username, setUsername] = useState(session.username ?? "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  // Enter on the password field and the button share one guarded submit: no double sign-in
  const inFlight = useRef(false);

  const canSubmit = !!username.trim() && !!password && !!serverUrl.trim();

  const login = async () => {
    if (inFlight.current || !canSubmit) return;
    inFlight.current = true;
    setLoading(true);
    setNotice(null);
    session.setServerUrl(serverUrl.trim());
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
      inFlight.current = false;
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={s.screen} keyboardShouldPersistTaps="handled">
          <View style={s.brand}>
            <View style={s.logo}>
              <MaterialCommunityIcons name="barcode-scan" size={40} color={c.onPrimary} />
            </View>
            <Text style={s.title}>WMS PDA</Text>
            <Text style={s.subtitle}>Sign in to start scanning</Text>
          </View>

          <Banner notice={notice} />

          <Card>
            <Field
              label="Username"
              value={username}
              onChangeText={setUsername}
              testID="username"
              textContentType="username"
              autoComplete="username"
              returnKeyType="next"
            />
            <Field
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              testID="password"
              textContentType="password"
              autoComplete="password"
              returnKeyType="go"
              onSubmitEditing={() => void login()}
              right={
                <IconButton
                  icon={showPassword ? "eye-off-outline" : "eye-outline"}
                  label={showPassword ? "Hide password" : "Show password"}
                  onPress={() => setShowPassword((v) => !v)}
                />
              }
            />
            <Button title="Sign in" icon="login" onPress={() => void login()} loading={loading} disabled={!canSubmit} testID="login" />
          </Card>

          <Card title="Server" icon="server-network">
            <Field label="Server URL" value={serverUrl} onChangeText={setServerUrl} testID="server-url" keyboardType="url" />
            <Text style={s.hint}>e.g. http://192.168.1.10:8000/api/v1 (ask your system administrator)</Text>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    screen: { padding: space.lg, gap: space.lg, flexGrow: 1, justifyContent: "center", maxWidth: 520, width: "100%", alignSelf: "center" },
    brand: { alignItems: "center", gap: space.xs, marginBottom: space.sm },
    logo: {
      width: 76,
      height: 76,
      borderRadius: radius.lg + 4,
      backgroundColor: c.primary,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: space.sm,
    },
    title: { ...type.title, fontSize: 26, color: c.text },
    subtitle: { fontSize: 15, color: c.textMuted },
    hint: { fontSize: 13, color: c.textMuted, marginTop: -space.xs },
  });
