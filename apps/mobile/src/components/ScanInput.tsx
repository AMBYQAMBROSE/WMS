import { useEffect, useRef, useState, type ComponentRef } from "react";
import { useIsFocused } from "expo-router";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors } from "@/components/ui";

interface Props {
  label: string;
  placeholder?: string;
  onScan: (code: string) => void;
  /** When false, do not grab focus (e.g. while a quantity panel is open) */
  active?: boolean;
  testID?: string;
}

/**
 * Scanners work as keyboard wedges: the barcode arrives as typed text followed by Enter.
 * The input keeps focus, clears and refocuses after each scan, and does not show the soft keyboard by default (it would cover the screen); tap "Keyboard" to type by hand.
 * Uncontrolled input read via ref: scanners type very fast and a controlled input re-renders per character, which can drop characters on low-end PDAs.
 */
export default function ScanInput({ label, placeholder, onScan, active = true, testID }: Props) {
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
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.row}>
        <TextInput
          ref={inputRef}
          testID={testID}
          style={[styles.input, !active && styles.inactive]}
          placeholder={placeholder ?? "Scan or type, then Enter"}
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
        <Pressable style={styles.kb} onPress={toggleKeyboard}>
          <Text style={styles.kbText}>{keyboard ? "Hide" : "Keyboard"}</Text>
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

const styles = StyleSheet.create({
  wrap: { marginBottom: 12 },
  label: { fontSize: 16, fontWeight: "600", marginBottom: 6, color: colors.text },
  row: { flexDirection: "row", gap: 8 },
  input: {
    flex: 1,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 20,
    backgroundColor: "#fff",
  },
  inactive: { borderColor: colors.border, backgroundColor: colors.muted },
  kb: {
    justifyContent: "center",
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
  },
  kbText: { fontSize: 14, color: colors.text },
});
