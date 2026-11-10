import { useState, type ComponentProps, type ReactNode } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";

import { useSettings } from "@/stores/settings";
import { noWebOutline, radius, size, space, tone as toneOf, type, useStyles, useTheme, type Palette, type Tone } from "@/theme";

export type IconName = ComponentProps<typeof MaterialCommunityIcons>["name"];

export function Icon({ name, size: s = 22, color }: { name: IconName; size?: number; color?: string }) {
  const { c } = useTheme();
  return <MaterialCommunityIcons name={name} size={s} color={color ?? c.textSecondary} />;
}

// ---------------------------------------------------------------------------------------------------------------
// Buttons

type ButtonVariant = "primary" | "secondary" | "default" | "danger" | "ghost";

export function Button({
  title,
  onPress,
  disabled,
  loading,
  variant = "primary",
  icon,
  compact,
  testID,
  style,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  /** "default" is kept as an alias of "secondary" */
  variant?: ButtonVariant;
  icon?: IconName;
  /** 44 dp instead of 52, for buttons inside a card */
  compact?: boolean;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const v = variant === "default" ? "secondary" : variant;
  const look = {
    primary: { bg: c.primary, pressed: c.primaryPressed, fg: c.onPrimary, border: c.primary },
    secondary: { bg: c.surface, pressed: c.surfaceAlt, fg: c.text, border: c.borderStrong },
    danger: { bg: c.surface, pressed: c.dangerTint, fg: c.dangerText, border: c.danger },
    ghost: { bg: "transparent", pressed: c.surfaceAlt, fg: c.primaryText, border: "transparent" },
  }[v];
  const off = disabled || loading;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      onPress={onPress}
      disabled={off}
      style={({ pressed }) => [
        s.button,
        compact && { minHeight: 44 },
        { backgroundColor: pressed ? look.pressed : look.bg, borderColor: look.border },
        disabled && !loading && s.disabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={look.fg} />
      ) : (
        <View style={s.buttonInner}>
          {icon && <MaterialCommunityIcons name={icon} size={20} color={look.fg} />}
          <Text style={[s.buttonText, { color: look.fg }]} numberOfLines={1}>
            {title}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

/** Square 48 dp icon button: delete, keyboard toggle, refresh, ... */
export function IconButton({
  icon,
  onPress,
  label,
  tone = "neutral",
  disabled,
  loading,
  filled,
  testID,
}: {
  icon: IconName;
  onPress: () => void;
  /** Screen-reader label (icon buttons have no visible text) */
  label: string;
  tone?: Tone;
  disabled?: boolean;
  loading?: boolean;
  filled?: boolean;
  testID?: string;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const t = toneOf(c, tone);
  const fg = tone === "neutral" ? c.textSecondary : t.text;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled || loading}
      hitSlop={4}
      style={({ pressed }) => [
        s.iconButton,
        filled && { backgroundColor: t.tint },
        pressed && { backgroundColor: tone === "neutral" ? c.border : t.tint },
        disabled && s.disabled,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <MaterialCommunityIcons name={icon} size={22} color={fg} />}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Feedback

export type BannerKind = "error" | "success" | "warning" | "info";

export interface Notice {
  kind: BannerKind;
  text: string;
}

const KIND_TONE: Record<BannerKind, Tone> = { error: "danger", success: "success", warning: "warning", info: "info" };
export const KIND_ICON: Record<BannerKind, IconName> = {
  error: "alert-circle",
  success: "check-circle",
  warning: "alert",
  info: "information",
};

/** Inline notice with an optional action ("Sign in", "Update now") */
export function Banner({
  notice,
  action,
  testID = "banner",
}: {
  notice: Notice | null;
  action?: { title: string; onPress: () => void; loading?: boolean; testID?: string };
  testID?: string;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  if (!notice) return null;
  const t = toneOf(c, KIND_TONE[notice.kind]);
  return (
    <View testID={testID} style={[s.banner, { backgroundColor: t.tint, borderColor: t.fill }]}>
      <View style={s.bannerBody}>
        <MaterialCommunityIcons name={KIND_ICON[notice.kind]} size={22} color={t.text} />
        <Text style={[s.bannerText, { color: t.text }]}>{notice.text}</Text>
      </View>
      {action && (
        <Pressable
          testID={action.testID}
          accessibilityRole="button"
          onPress={action.onPress}
          disabled={action.loading}
          style={({ pressed }) => [s.bannerAction, { borderColor: t.fill, opacity: pressed ? 0.7 : 1 }]}
        >
          {action.loading ? (
            <ActivityIndicator color={t.text} />
          ) : (
            <Text style={[s.bannerActionText, { color: t.text }]}>{action.title}</Text>
          )}
        </Pressable>
      )}
    </View>
  );
}

export function Pill({ text, tone = "neutral", icon }: { text: string; tone?: Tone; icon?: IconName }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const t = toneOf(c, tone);
  return (
    <View style={[s.pill, { backgroundColor: t.tint }]}>
      {icon && <MaterialCommunityIcons name={icon} size={14} color={t.text} />}
      <Text style={[s.pillText, { color: t.text }]} numberOfLines={1}>
        {text}
      </Text>
    </View>
  );
}

export function ProgressBar({ value, tone = "primary" }: { value: number; tone?: Tone }) {
  const { c } = useTheme();
  const t = toneOf(c, tone);
  const pct = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(pct * 100) }}
      style={{ height: 6, borderRadius: 3, backgroundColor: c.border, overflow: "hidden" }}
    >
      <View style={{ width: `${pct * 100}%`, height: "100%", borderRadius: 3, backgroundColor: t.fill }} />
    </View>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Inputs

export function Field({
  label,
  error,
  right,
  style,
  onFocus,
  onBlur,
  ...props
}: TextInputProps & { label: string; error?: string | null; right?: ReactNode }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const [focused, setFocused] = useState(false);
  return (
    <View style={s.field}>
      <Text style={s.fieldLabel}>{label}</Text>
      <View
        style={[
          s.fieldBox,
          focused && { borderColor: c.primary, backgroundColor: c.surface },
          !!error && { borderColor: c.danger },
        ]}
      >
        <TextInput
          style={[s.fieldInput, style]}
          autoCapitalize="none"
          autoCorrect={false}
          placeholderTextColor={c.textMuted}
          accessibilityLabel={label}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...props}
        />
        {right}
      </View>
      {!!error && <Text style={s.fieldError}>{error}</Text>}
    </View>
  );
}

/** Quantity with large tabular digits and −/+ steppers (for gloves: no need to open the keyboard for small changes) */
export function QtyField({
  label,
  value,
  onChangeText,
  unit,
  min = 0,
  testID,
  ...props
}: Omit<TextInputProps, "value" | "onChangeText"> & {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  unit?: string;
  min?: number;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const [focused, setFocused] = useState(false);
  const stepBy = (d: number) => {
    const n = Number(value.trim());
    const base = value.trim() === "" || !Number.isFinite(n) ? 0 : n;
    const next = Math.max(min, Math.round((base + d) * 10000) / 10000);
    onChangeText(String(next));
  };
  return (
    <View style={s.field}>
      <Text style={s.fieldLabel}>{label}</Text>
      <View style={s.qtyRow}>
        <IconButton icon="minus" label="Decrease" onPress={() => stepBy(-1)} filled tone="primary" />
        <View style={[s.qtyBox, focused && { borderColor: c.primary }]}>
          <TextInput
            testID={testID}
            style={s.qtyInput}
            value={value}
            onChangeText={onChangeText}
            keyboardType="decimal-pad"
            selectTextOnFocus
            accessibilityLabel={label}
            placeholderTextColor={c.textMuted}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            {...props}
          />
          {unit && <Text style={s.qtyUnit}>{unit}</Text>}
        </View>
        <IconButton icon="plus" label="Increase" onPress={() => stepBy(1)} filled tone="primary" />
      </View>
    </View>
  );
}

/** Segmented control (e.g. theme: System / Light / Dark) */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; icon?: IconName }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  return (
    <View style={s.segmented} accessibilityRole="radiogroup">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            onPress={() => onChange(o.value)}
            style={[s.segment, on && { backgroundColor: c.surface, borderColor: c.border }]}
          >
            {o.icon && <MaterialCommunityIcons name={o.icon} size={18} color={on ? c.primaryText : c.textMuted} />}
            <Text style={[s.segmentText, { color: on ? c.text : c.textMuted }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Layout

export function Card({
  children,
  title,
  icon,
  right,
  testID,
  style,
}: {
  children?: ReactNode;
  title?: string;
  icon?: IconName;
  right?: ReactNode;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const s = useStyles(makeStyles);
  const { c } = useTheme();
  return (
    <View style={[s.card, style]} testID={testID}>
      {(title || right) && (
        <View style={s.cardHeader}>
          <View style={s.cardTitleRow}>
            {icon && <MaterialCommunityIcons name={icon} size={20} color={c.primaryText} />}
            {title && <Text style={s.cardTitle}>{title}</Text>}
          </View>
          {right}
        </View>
      )}
      {children}
    </View>
  );
}

export function Row({ label, value, strong }: { label: string; value: ReactNode; strong?: boolean }) {
  const s = useStyles(makeStyles);
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={[s.rowValue, strong && { fontWeight: "700" }]}>{value}</Text>
    </View>
  );
}

/** Label above a big value, for summary numbers */
export function Stat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const s = useStyles(makeStyles);
  const { c } = useTheme();
  return (
    <View style={s.stat}>
      <Text style={s.statLabel}>{label}</Text>
      <Text style={[s.statValue, tone !== "neutral" && { color: toneOf(c, tone).text }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

export function SectionHeader({ title, count, right }: { title: string; count?: number; right?: ReactNode }) {
  const s = useStyles(makeStyles);
  return (
    <View style={s.sectionHeader}>
      <Text style={s.sectionTitle}>
        {title}
        {count !== undefined && <Text style={s.sectionCount}>{`  ${count}`}</Text>}
      </Text>
      {right}
    </View>
  );
}

/** A tappable list row: title, optional subtitle, trailing content and a chevron */
export function ListRow({
  title,
  subtitle,
  icon,
  right,
  onPress,
  disabled,
  testID,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: IconName;
  right?: ReactNode;
  onPress?: () => void;
  disabled?: boolean;
  testID?: string;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const body = (
    <>
      {icon && (
        <View style={s.listIcon}>
          <MaterialCommunityIcons name={icon} size={22} color={c.primaryText} />
        </View>
      )}
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.listTitle}>{title}</Text>
        {subtitle ? <Text style={s.listSubtitle}>{subtitle}</Text> : null}
      </View>
      {right}
      {onPress && <MaterialCommunityIcons name="chevron-right" size={24} color={c.textMuted} />}
    </>
  );
  if (!onPress) return <View style={s.listRow}>{body}</View>;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [s.listRow, s.listRowTap, pressed && { backgroundColor: c.surfaceAlt }]}
    >
      {body}
    </Pressable>
  );
}

export function Divider() {
  const { c } = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: c.border }} />;
}

export function EmptyState({ icon, title, text, children }: { icon: IconName; title: string; text?: string; children?: ReactNode }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  return (
    <View style={s.empty}>
      <View style={s.emptyIcon}>
        <MaterialCommunityIcons name={icon} size={36} color={c.primaryText} />
      </View>
      <Text style={s.emptyTitle}>{title}</Text>
      {text && <Text style={s.emptyText}>{text}</Text>}
      {children}
    </View>
  );
}

/** Device setting shown on scanning screens: "Each scan counts 1" (stores/settings.ts) */
export function EachScanToggle({ testID = "each-scan" }: { testID?: string }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const on = useSettings((st) => st.eachScanCountsOne);
  const setOn = useSettings((st) => st.setEachScanCountsOne);
  return (
    <View style={[s.toggle, on && { borderColor: c.primary, backgroundColor: c.primaryTint }]}>
      <MaterialCommunityIcons name="counter" size={22} color={on ? c.primaryText : c.textMuted} />
      <View style={{ flex: 1 }}>
        <Text style={s.toggleTitle}>Each scan counts 1</Text>
        <Text style={s.toggleHint}>For goods labelled per unit: scan every piece instead of typing a quantity</Text>
      </View>
      <Switch
        value={on}
        onValueChange={setOn}
        testID={testID}
        accessibilityLabel="Each scan counts 1"
        trackColor={{ true: c.primary, false: c.borderStrong }}
        thumbColor={c.surface}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------------------------------------------

export const makeStyles = (c: Palette) =>
  StyleSheet.create({
    button: {
      minHeight: size.button,
      borderRadius: radius.md,
      borderWidth: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: space.lg,
    },
    buttonInner: { flexDirection: "row", alignItems: "center", gap: space.sm },
    buttonText: { fontSize: 17, fontWeight: "600" },
    disabled: { opacity: 0.45 },
    iconButton: {
      width: size.touch,
      height: size.touch,
      borderRadius: radius.md,
      alignItems: "center",
      justifyContent: "center",
    },
    banner: { borderRadius: radius.md, borderLeftWidth: 4, padding: space.md, gap: space.sm },
    bannerBody: { flexDirection: "row", gap: space.sm, alignItems: "flex-start" },
    bannerText: { ...type.body, fontWeight: "500", flex: 1, lineHeight: 22 },
    bannerAction: {
      alignSelf: "flex-start",
      marginLeft: 30,
      minHeight: 40,
      paddingHorizontal: space.lg,
      borderRadius: radius.sm,
      borderWidth: 1,
      justifyContent: "center",
    },
    bannerActionText: { fontSize: 15, fontWeight: "600" },
    pill: {
      flexDirection: "row",
      alignItems: "center",
      gap: 4,
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: radius.pill,
      alignSelf: "flex-start",
    },
    pillText: { fontSize: 13, fontWeight: "600", fontVariant: ["tabular-nums"] },
    field: { gap: 6 },
    fieldLabel: { ...type.label, color: c.textSecondary },
    fieldBox: {
      flexDirection: "row",
      alignItems: "center",
      minHeight: size.input,
      borderWidth: 1.5,
      borderColor: c.border,
      borderRadius: radius.md,
      backgroundColor: c.surfaceAlt,
      paddingRight: 2,
    },
    fieldInput: { flex: 1, minWidth: 0, paddingHorizontal: space.md, paddingVertical: 10, fontSize: 18, color: c.text, ...noWebOutline },
    fieldError: { ...type.caption, color: c.dangerText },
    qtyRow: { flexDirection: "row", alignItems: "center", gap: space.sm },
    qtyBox: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      minHeight: 60,
      borderWidth: 1.5,
      borderColor: c.border,
      borderRadius: radius.md,
      backgroundColor: c.surface,
      paddingHorizontal: space.md,
    },
    qtyInput: {
      flex: 1,
      minWidth: 0,
      fontSize: 28,
      fontWeight: "700",
      color: c.text,
      textAlign: "center",
      fontVariant: ["tabular-nums"],
      paddingVertical: 6,
      ...noWebOutline,
    },
    qtyUnit: { ...type.label, color: c.textMuted },
    segmented: {
      flexDirection: "row",
      backgroundColor: c.surfaceAlt,
      borderRadius: radius.md,
      padding: 4,
      gap: 4,
      borderWidth: 1,
      borderColor: c.border,
    },
    segment: {
      flex: 1,
      flexDirection: "row",
      gap: 6,
      minHeight: 40,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: radius.sm,
      borderWidth: 1,
      borderColor: "transparent",
    },
    segmentText: { fontSize: 14, fontWeight: "600" },
    card: {
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      padding: space.lg,
      gap: space.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
    },
    cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.sm },
    cardTitleRow: { flexDirection: "row", alignItems: "center", gap: space.sm, flexShrink: 1 },
    cardTitle: { ...type.heading, color: c.text },
    row: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: space.md },
    rowLabel: { ...type.label, fontWeight: "400", color: c.textMuted },
    rowValue: { fontSize: 15, color: c.text, flexShrink: 1, textAlign: "right", fontWeight: "500" },
    stat: { flex: 1, gap: 2 },
    statLabel: { ...type.overline, color: c.textMuted },
    statValue: { fontSize: 22, fontWeight: "700", color: c.text, fontVariant: ["tabular-nums"] },
    sectionHeader: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: space.xs,
      marginTop: space.sm,
    },
    sectionTitle: { ...type.overline, color: c.textSecondary },
    sectionCount: { color: c.textMuted },
    listRow: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: space.sm },
    listRowTap: {
      minHeight: 64,
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
    },
    listIcon: {
      width: 40,
      height: 40,
      borderRadius: radius.md,
      backgroundColor: c.primaryTint,
      alignItems: "center",
      justifyContent: "center",
    },
    listTitle: { ...type.heading, color: c.text },
    listSubtitle: { ...type.caption, color: c.textMuted },
    empty: { alignItems: "center", gap: space.sm, paddingVertical: space.xxl, paddingHorizontal: space.xl },
    emptyIcon: {
      width: 72,
      height: 72,
      borderRadius: 36,
      backgroundColor: c.primaryTint,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: space.sm,
    },
    emptyTitle: { ...type.heading, color: c.text, textAlign: "center" },
    emptyText: { ...type.body, color: c.textMuted, textAlign: "center", lineHeight: 22 },
    toggle: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.md,
      padding: space.md,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: c.border,
      backgroundColor: c.surface,
    },
    toggleTitle: { fontSize: 15, fontWeight: "600", color: c.text },
    toggleHint: { fontSize: 12, color: c.textMuted, lineHeight: 16 },
  });
