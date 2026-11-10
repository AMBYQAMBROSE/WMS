import { useCallback, useState } from "react";

import * as Haptics from "expo-haptics";
import { Alert, Platform } from "react-native";

import type { Notice } from "@/components/ui";

/** Feel the result without looking at the screen: operators usually watch the goods, not the PDA */
export function haptic(kind: Notice["kind"] | "tick") {
  const run = () => {
    switch (kind) {
      case "error":
        return Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      case "warning":
        return Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      case "success":
        return Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      case "tick":
        return Haptics.selectionAsync();
      default:
        return Promise.resolve();
    }
  };
  if (Platform.OS === "web") return;
  void run().catch(() => undefined);
}

/**
 * The screen's feedback message. Setting one also gives the matching haptic: errors buzz, so a wrong scan is never
 * silent. Pass `{ silent: true }` when the screen already gave its own haptic (e.g. the per-piece tick).
 */
export function useNotice() {
  const [notice, setNoticeState] = useState<Notice | null>(null);
  const setNotice = useCallback((next: Notice | null, opts?: { silent?: boolean }) => {
    setNoticeState(next);
    if (next && !opts?.silent) haptic(next.kind);
  }, []);
  return [notice, setNotice] as const;
}

/** Ask before discarding work. Alert on native; the browser build (E2E) uses window.confirm */
export function confirm(title: string, message: string, ok: string, onOk: () => void) {
  if (Platform.OS === "web") {
    const w = globalThis as { confirm?: (m: string) => boolean };
    if (!w.confirm || w.confirm(`${title}\n\n${message}`)) onOk();
    return;
  }
  Alert.alert(title, message, [
    { text: "Cancel", style: "cancel" },
    { text: ok, style: "destructive", onPress: onOk },
  ]);
}
