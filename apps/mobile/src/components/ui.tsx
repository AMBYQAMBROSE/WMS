import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type KeyboardTypeOptions,
  type TextInputProps,
} from "react-native";

export const colors = {
  primary: "#1677ff",
  danger: "#d4380d",
  success: "#389e0d",
  warning: "#d48806",
  text: "#1f1f1f",
  subtle: "#666",
  border: "#d9d9d9",
  muted: "#f5f5f5",
  bg: "#f0f2f5",
};

export function Button({
  title,
  onPress,
  disabled,
  loading,
  variant = "primary",
  testID,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "default" | "danger";
  testID?: string;
}) {
  const filled = variant === "primary";
  const tint = variant === "danger" ? colors.danger : colors.primary;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || loading}
      style={[
        styles.button,
        filled ? { backgroundColor: tint } : { borderWidth: 1, borderColor: variant === "danger" ? tint : colors.border },
        (disabled || loading) && styles.disabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={filled ? "#fff" : tint} />
      ) : (
        <Text style={[styles.buttonText, { color: filled ? "#fff" : variant === "danger" ? tint : colors.text }]}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

export type BannerKind = "error" | "success" | "warning" | "info";

export interface Notice {
  kind: BannerKind;
  text: string;
}

const BANNER_COLORS: Record<BannerKind, string> = {
  error: colors.danger,
  success: colors.success,
  warning: colors.warning,
  info: colors.primary,
};

export function Banner({ notice }: { notice: Notice | null }) {
  if (!notice) return null;
  const color = BANNER_COLORS[notice.kind];
  return (
    <View testID="banner" style={[styles.banner, { borderColor: color, backgroundColor: color + "14" }]}>
      <Text style={[styles.bannerText, { color }]}>{notice.text}</Text>
    </View>
  );
}

export function Field({
  label,
  keyboardType,
  ...props
}: TextInputProps & { label: string; keyboardType?: KeyboardTypeOptions }) {
  return (
    <View style={{ marginBottom: 10 }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={keyboardType}
        {...props}
      />
    </View>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { padding: 12, gap: 10, backgroundColor: colors.bg, flexGrow: 1 },
  button: {
    minHeight: 48,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
    backgroundColor: "#fff",
  },
  buttonText: { fontSize: 17, fontWeight: "600" },
  disabled: { opacity: 0.5 },
  banner: { borderWidth: 1, borderRadius: 8, padding: 10 },
  bannerText: { fontSize: 15, fontWeight: "500" },
  fieldLabel: { fontSize: 14, color: colors.subtle, marginBottom: 4 },
  fieldInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 18,
    backgroundColor: "#fff",
  },
  card: { backgroundColor: "#fff", borderRadius: 10, padding: 12, gap: 6 },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  rowLabel: { fontSize: 14, color: colors.subtle },
  rowValue: { fontSize: 15, color: colors.text, flexShrink: 1, textAlign: "right" },
  title: { fontSize: 18, fontWeight: "700", color: colors.text },
  hint: { fontSize: 13, color: colors.subtle },
});
