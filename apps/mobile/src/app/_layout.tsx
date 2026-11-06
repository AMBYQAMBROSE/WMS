import { useEffect } from "react";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, AppState, View } from "react-native";

import SyncIndicator from "@/components/SyncIndicator";
import { useHydrated } from "@/lib/useHydrated";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { TASK_CHECK_MS, useTasks } from "@/stores/tasks";

const SYNC_INTERVAL_MS = 20000;

export default function RootLayout() {
  const hydrated = useHydrated();
  const token = useSession((s) => s.token);

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

  if (!hydrated) {
    return (
      <View style={{ flex: 1, justifyContent: "center" }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerRight: () => <SyncIndicator /> }}>
        <Stack.Screen name="index" options={{ title: "WMS PDA" }} />
        <Stack.Screen name="login" options={{ title: "Sign in", headerRight: () => null }} />
        <Stack.Screen name="receive" options={{ title: "Receive" }} />
        <Stack.Screen name="putaway" options={{ title: "Put away" }} />
        <Stack.Screen name="move" options={{ title: "Move" }} />
        <Stack.Screen name="count" options={{ title: "Count" }} />
        <Stack.Screen name="pick" options={{ title: "Pick" }} />
        <Stack.Screen name="queue" options={{ title: "Submit queue" }} />
      </Stack>
    </>
  );
}
