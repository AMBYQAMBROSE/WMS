import { useEffect, useMemo } from "react";

import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import * as SystemUI from "expo-system-ui";
import { ActivityIndicator, AppState, View } from "react-native";

import SyncIndicator from "@/components/SyncIndicator";
import { useHydrated } from "@/lib/useHydrated";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { TASK_CHECK_MS, useTasks } from "@/stores/tasks";
import { useTheme } from "@/theme";

const SYNC_INTERVAL_MS = 20000;

export default function RootLayout() {
  const hydrated = useHydrated();
  const token = useSession((s) => s.token);
  const { c, dark } = useTheme();

  useEffect(() => {
    if (!hydrated || !token) return;
    const { sync } = useQueue.getState();
    void sync();
    const hasPending = () => useQueue.getState().ops.some((o) => o.status === "pending");
    const timer = setInterval(() => {
      if (hasPending()) void sync();
    }, SYNC_INTERVAL_MS);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void sync();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, [hydrated, token]);

  // New-work alerts (stores/tasks.ts); a new sign-in starts from a fresh baseline
  useEffect(() => {
    if (!hydrated || !token) return;
    const { reset, check } = useTasks.getState();
    reset();
    void check();
    const timer = setInterval(() => void useTasks.getState().check(), TASK_CHECK_MS);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void useTasks.getState().check();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, [hydrated, token]);

  // Root background behind screens and transitions, so dark mode never flashes white
  useEffect(() => {
    void SystemUI.setBackgroundColorAsync(c.bg).catch(() => undefined);
  }, [c.bg]);

  const navTheme = useMemo(() => {
    const base = dark ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: { ...base.colors, primary: c.primary, background: c.bg, card: c.surface, text: c.text, border: c.border },
    };
  }, [c, dark]);

  if (!hydrated) {
    return (
      <View style={{ flex: 1, justifyContent: "center", backgroundColor: c.bg }}>
        <ActivityIndicator size="large" color={c.primary} />
      </View>
    );
  }

  return (
    <ThemeProvider value={navTheme}>
      <StatusBar style={dark ? "light" : "dark"} />
      <Stack
        screenOptions={{
          headerRight: () => <SyncIndicator />,
          headerStyle: { backgroundColor: c.surface },
          headerTintColor: c.text,
          headerTitleStyle: { fontWeight: "700", fontSize: 18 },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: c.bg },
          animation: "slide_from_right",
        }}
      >
        <Stack.Screen name="index" options={{ title: "WMS PDA" }} />
        <Stack.Screen name="login" options={{ headerShown: false }} />
        <Stack.Screen name="receive" options={{ title: "Receive" }} />
        <Stack.Screen name="putaway" options={{ title: "Put away" }} />
        <Stack.Screen name="putaway-free" options={{ title: "Put away without a sheet" }} />
        <Stack.Screen name="move" options={{ title: "Move" }} />
        <Stack.Screen name="count" options={{ title: "Count" }} />
        <Stack.Screen name="pick" options={{ title: "Pick" }} />
        <Stack.Screen name="queue" options={{ title: "Submit queue" }} />
      </Stack>
    </ThemeProvider>
  );
}
