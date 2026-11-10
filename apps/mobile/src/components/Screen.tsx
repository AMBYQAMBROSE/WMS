import { Fragment, useEffect, useState, type ReactElement, type ReactNode } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  AccessibilityInfo,
  Animated,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type RefreshControlProps,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { KIND_ICON, type IconName, type Notice } from "@/components/ui";
import { radius, space, tone, type, useStyles, useTheme, type Palette } from "@/theme";

const KIND_TONE = { error: "danger", success: "success", warning: "warning", info: "info" } as const;

/**
 * Scan screen skeleton. The step indicator and the feedback toast sit above the scroll area, so a "Wrong bin" or
 * "Rejected" message is never scrolled out of view; the primary action lives in a fixed bottom bar.
 */
export default function Screen({
  children,
  notice,
  onDismiss,
  steps,
  step = 0,
  footer,
  refreshControl,
}: {
  children: ReactNode;
  notice?: Notice | null;
  onDismiss?: () => void;
  steps?: string[];
  step?: number;
  footer?: ReactNode;
  refreshControl?: ReactElement<RefreshControlProps>;
}) {
  const s = useStyles(makeStyles);
  const insets = useSafeAreaInsets();
  return (
    <View style={s.root}>
      {steps && <StepIndicator steps={steps} current={step} />}
      <Toast notice={notice ?? null} onDismiss={onDismiss} />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
        refreshControl={refreshControl}
      >
        {children}
      </ScrollView>
      {footer && <View style={[s.footer, { paddingBottom: Math.max(insets.bottom, space.md) }]}>{footer}</View>}
    </View>
  );
}

export function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  return (
    <View style={s.steps} accessibilityRole="progressbar" accessibilityLabel={`Step ${current + 1} of ${steps.length}: ${steps[current]}`}>
      {steps.map((label, i) => {
        const done = i < current;
        const on = i === current;
        return (
          <Fragment key={label}>
            {i > 0 && <View style={[s.stepLine, { backgroundColor: i <= current ? c.primary : c.border }]} />}
            <View style={s.step}>
              <View
                style={[
                  s.stepDot,
                  done && { backgroundColor: c.primary, borderColor: c.primary },
                  on && { borderColor: c.primary, backgroundColor: c.primaryTint },
                ]}
              >
                {done ? (
                  <MaterialCommunityIcons name="check" size={14} color={c.onPrimary} />
                ) : (
                  <Text style={[s.stepNum, on && { color: c.primaryText }]}>{i + 1}</Text>
                )}
              </View>
              <Text style={[s.stepLabel, (on || done) && { color: on ? c.text : c.textSecondary }, on && { fontWeight: "700" }]} numberOfLines={1}>
                {label}
              </Text>
            </View>
          </Fragment>
        );
      })}
    </View>
  );
}

/** The latest result, pinned under the header; slides in on every new message and stays until the next one */
export function Toast({ notice, onDismiss }: { notice: Notice | null; onDismiss?: () => void }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const [anim] = useState(() => new Animated.Value(0));
  const [slide] = useState(() => anim.interpolate({ inputRange: [0, 1], outputRange: [-8, 0] }));

  useEffect(() => {
    if (!notice) return;
    anim.setValue(0);
    Animated.timing(anim, { toValue: 1, duration: 180, useNativeDriver: Platform.OS !== "web" }).start();
    AccessibilityInfo.announceForAccessibility?.(notice.text);
  }, [notice, anim]);

  if (!notice) return null;
  const t = tone(c, KIND_TONE[notice.kind]);
  return (
    <Animated.View
      testID="banner"
      accessibilityLiveRegion="polite"
      style={[
        s.toast,
        { backgroundColor: t.tint, borderColor: t.fill },
        { opacity: anim, transform: [{ translateY: slide }] },
      ]}
    >
      <MaterialCommunityIcons name={KIND_ICON[notice.kind]} size={24} color={t.text} />
      <Text style={[s.toastText, { color: t.text }]}>{notice.text}</Text>
      {onDismiss && (
        <Pressable accessibilityRole="button" accessibilityLabel="Dismiss" onPress={onDismiss} hitSlop={10} style={s.toastClose}>
          <MaterialCommunityIcons name="close" size={18} color={t.text} />
        </Pressable>
      )}
    </Animated.View>
  );
}

/** What the operator is working on (order, location, ...), with a single "Change" action */
export function ContextBar({
  items,
  onChange,
  changeLabel = "Change",
  badge,
}: {
  items: { icon: IconName; label: string; value: string; sub?: string }[];
  onChange?: () => void;
  changeLabel?: string;
  badge?: ReactNode;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  return (
    <View style={s.context}>
      <View style={{ flex: 1, gap: space.sm }}>
        {items.map((it) => (
          <View key={it.label} style={s.contextItem}>
            <View style={s.contextIcon}>
              <MaterialCommunityIcons name={it.icon} size={18} color={c.primaryText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.contextLabel}>{it.label}</Text>
              <Text style={s.contextValue} numberOfLines={1}>
                {it.value}
              </Text>
              {it.sub ? (
                <Text style={s.contextSub} numberOfLines={1}>
                  {it.sub}
                </Text>
              ) : null}
            </View>
          </View>
        ))}
        {badge}
      </View>
      {onChange && (
        <Pressable
          accessibilityRole="button"
          onPress={onChange}
          style={({ pressed }) => [s.contextChange, pressed && { backgroundColor: c.primaryTint }]}
        >
          <Text style={s.contextChangeText}>{changeLabel}</Text>
        </Pressable>
      )}
    </View>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: c.bg },
    content: { padding: space.lg, gap: space.md, flexGrow: 1 },
    footer: {
      paddingHorizontal: space.lg,
      paddingTop: space.md,
      gap: space.sm,
      backgroundColor: c.surface,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.border,
    },
    steps: {
      flexDirection: "row",
      alignItems: "flex-start",
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      backgroundColor: c.surface,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: c.border,
    },
    step: { alignItems: "center", gap: 4, maxWidth: 96 },
    stepDot: {
      width: 26,
      height: 26,
      borderRadius: 13,
      borderWidth: 2,
      borderColor: c.borderStrong,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: c.surface,
    },
    stepNum: { fontSize: 13, fontWeight: "700", color: c.textMuted },
    stepLabel: { fontSize: 12, color: c.textMuted },
    stepLine: { flex: 1, height: 2, marginTop: 12, marginHorizontal: 4, borderRadius: 1 },
    toast: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.sm,
      marginHorizontal: space.lg,
      marginTop: space.md,
      paddingVertical: space.md,
      paddingLeft: space.md,
      paddingRight: space.sm,
      borderRadius: radius.md,
      borderLeftWidth: 5,
    },
    toastText: { ...type.body, fontWeight: "600", flex: 1, lineHeight: 22 },
    toastClose: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
    context: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: space.md,
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      padding: space.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
    },
    contextItem: { flexDirection: "row", alignItems: "center", gap: space.sm },
    contextIcon: {
      width: 32,
      height: 32,
      borderRadius: radius.sm,
      backgroundColor: c.primaryTint,
      alignItems: "center",
      justifyContent: "center",
    },
    contextLabel: { fontSize: 12, color: c.textMuted },
    contextValue: { fontSize: 17, fontWeight: "700", color: c.text },
    contextSub: { fontSize: 14, fontWeight: "400", color: c.textSecondary },
    contextChange: {
      minHeight: 40,
      paddingHorizontal: space.md,
      borderRadius: radius.sm,
      justifyContent: "center",
      borderWidth: 1,
      borderColor: c.border,
    },
    contextChangeText: { fontSize: 15, fontWeight: "600", color: c.primaryText },
  });
