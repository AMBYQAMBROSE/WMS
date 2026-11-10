import { useEffect, useRef, useState, type ComponentRef } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useIsFocused } from "expo-router";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { noWebOutline, radius, size, space, useStyles, useTheme, type Palette } from "@/theme";

interface Props {
  label: string;
  placeholder?: string;
  onScan: (code: string) => void;
  /** When false, do not grab focus (e.g. while a quantity panel is open) */
  active?: boolean;
  /** Icon in the field, matching what is scanned (bin, item, document) */
  icon?: "barcode-scan" | "map-marker-radius" | "file-document-outline" | "package-variant-closed";
  testID?: string;
}

/**
 * Scanners work as keyboard wedges: the barcode arrives as typed text followed by Enter.
 * The input keeps focus, clears and refocuses after each scan, and does not show the soft keyboard by default (it would cover the screen); tap the keyboard button to type by hand.
 * Uncontrolled input read via ref: scanners type very fast and a controlled input re-renders per character, which can drop characters on low-end PDAs.
 */
export default function ScanInput({ label, placeholder, onScan, active = true, icon = "barcode-scan", testID }: Props) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const inputRef = useRef<ComponentRef<typeof TextInput>>(null);
  const valueRef = useRef("");
  const [keyboard, setKeyboard] = useState(false);

  const focus = () => setTimeout(() => inputRef.current?.focus(), 0);

  // Covered screens in the stack stay mounted; only the visible screen may grab focus
  const screenFocused = useIsFocused();

  useEffect(() => {
    if (!active || !screenFocused) return;
    focus();
    // After the operator taps a button (submit, delete, ...) focus sits on the button and the next scan's characters are lost.
    // Whenever no input is in use, take focus back; never steal focus from other inputs such as quantity.
    const guard = setInterval(() => {
      if (!isAnyInputFocused()) inputRef.current?.focus();
    }, FOCUS_GUARD_MS);
    return () => clearInterval(guard);
  }, [active, screenFocused]);

  const submit = () => {
    const code = valueRef.current.trim();
    valueRef.current = "";
    inputRef.current?.clear();
    if (code) onScan(code);
    if (active) focus();
  };

  // Check on the next tick after blur: scanning right after tapping a button loses no characters (the timer is only a fallback)
  const handleBlur = () => {
    if (!active || !screenFocused) return;
    setTimeout(() => {
      if (!isAnyInputFocused()) inputRef.current?.focus();
    }, 0);
  };

  const toggleKeyboard = () => {
    setKeyboard((k) => !k);
    // showSoftInputOnFocus only applies on focus, so refocus after toggling
    inputRef.current?.blur();
    focus();
  };

  return (
    <View style={s.wrap}>
      <View style={s.labelRow}>
        <Text style={s.label}>{label}</Text>
        {active && (
          <View style={s.ready}>
            <View style={[s.readyDot, { backgroundColor: c.success }]} />
            <Text style={s.readyText}>Ready</Text>
          </View>
        )}
      </View>
      <View style={[s.box, active ? s.boxActive : s.boxInactive]}>
        <MaterialCommunityIcons name={icon} size={26} color={active ? c.primaryText : c.textMuted} style={{ marginLeft: space.md }} />
        <TextInput
          ref={inputRef}
          testID={testID}
          accessibilityLabel={label}
          style={s.input}
          placeholder={placeholder ?? (active ? "Scan or type + Enter" : "Waiting…")}
          placeholderTextColor={c.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
          autoFocus={active}
          editable={active}
          {...keepFocusOnSubmit}
          showSoftInputOnFocus={keyboard}
          returnKeyType="done"
          onChangeText={(text) => {
            valueRef.current = text;
          }}
          onSubmitEditing={submit}
          onBlur={handleBlur}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={keyboard ? "Hide keyboard" : "Type with keyboard"}
          onPress={toggleKeyboard}
          disabled={!active}
          style={({ pressed }) => [s.kb, keyboard && { backgroundColor: c.primaryTint }, pressed && { backgroundColor: c.border }]}
        >
          <MaterialCommunityIcons name={keyboard ? "keyboard-off-outline" : "keyboard-outline"} size={24} color={keyboard ? c.primaryText : c.textSecondary} />
        </Pressable>
      </View>
    </View>
  );
}

const FOCUS_GUARD_MS = 500;

function isAnyInputFocused(): boolean {
  if (Platform.OS === "web") {
    const tag = (globalThis as { document?: Document }).document?.activeElement?.tagName;
    return tag === "INPUT" || tag === "TEXTAREA";
  }
  return TextInput.State.currentlyFocusedInput() != null;
}

// Do not blur on Enter, or the next scan's characters have nowhere to go.
// Native uses submitBehavior; react-native-web ignores it and only honors the deprecated blurOnSubmit (which blurs on the next tick by default)
const keepFocusOnSubmit =
  Platform.OS === "web" ? { blurOnSubmit: false } : ({ submitBehavior: "submit" } as const);

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    wrap: { gap: space.sm },
    labelRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    label: { fontSize: 17, fontWeight: "700", color: c.text, flexShrink: 1 },
    ready: { flexDirection: "row", alignItems: "center", gap: 6 },
    readyDot: { width: 8, height: 8, borderRadius: 4 },
    readyText: { fontSize: 13, fontWeight: "600", color: c.successText },
    box: {
      flexDirection: "row",
      alignItems: "center",
      minHeight: size.scan,
      borderRadius: radius.md,
      borderWidth: 2,
    },
    boxActive: { borderColor: c.primary, backgroundColor: c.surface },
    boxInactive: { borderColor: c.border, backgroundColor: c.surfaceAlt },
    input: {
      flex: 1,
      minWidth: 0,
      paddingHorizontal: space.md,
      paddingVertical: 12,
      fontSize: 20,
      fontWeight: "600",
      color: c.text,
      ...noWebOutline,
    },
    kb: {
      width: size.touch,
      height: size.touch,
      marginRight: 4,
      borderRadius: radius.sm,
      alignItems: "center",
      justifyContent: "center",
    },
  });
