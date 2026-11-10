import { useMemo } from "react";

import { Platform, useColorScheme, type TextStyle } from "react-native";

import { useSettings } from "@/stores/settings";

/**
 * Design tokens. Same brand as the web console (apps/web/src/theme): one indigo accent on neutral layered surfaces.
 * Every "*Text" color is at least 4.5:1 on both `surface` and its own tint, for PDA screens in bright warehouse light.
 */
const light = {
  bg: "#f3f4f7",
  surface: "#ffffff",
  surfaceAlt: "#f7f8fa",
  border: "#e3e5ea",
  borderStrong: "#c9cdd5",
  text: "#0f1115",
  textSecondary: "#4b5160",
  textMuted: "#6b7180",
  primary: "#4f46e5",
  primaryPressed: "#4338ca",
  primaryText: "#4338ca",
  primaryTint: "#eef0ff",
  onPrimary: "#ffffff",
  success: "#15803d",
  successText: "#166534",
  successTint: "#e8f6ec",
  warning: "#b45309",
  warningText: "#92400e",
  warningTint: "#fdf3e1",
  danger: "#dc2626",
  dangerText: "#b91c1c",
  dangerTint: "#fdecec",
  info: "#2563eb",
  infoText: "#1d4ed8",
  infoTint: "#e9f0fe",
  overlay: "rgba(15, 17, 21, 0.45)",
  shadow: "#0f1115",
};

export type Palette = typeof light;

const dark: Palette = {
  bg: "#0e0f12",
  surface: "#17181c",
  surfaceAlt: "#1d1e23",
  border: "#2a2c33",
  borderStrong: "#3a3d46",
  text: "#ecedef",
  textSecondary: "#b0b4bd",
  textMuted: "#8a8f99",
  primary: "#5753e8",
  primaryPressed: "#4a46d6",
  primaryText: "#a3a5ff",
  primaryTint: "#1f2042",
  onPrimary: "#ffffff",
  success: "#22c55e",
  successText: "#4ade80",
  successTint: "#11281a",
  warning: "#f59e0b",
  warningText: "#fbbf24",
  warningTint: "#2c2109",
  danger: "#f05252",
  dangerText: "#f87171",
  dangerTint: "#2f1517",
  info: "#4f8ff7",
  infoText: "#8db4ff",
  infoTint: "#121f38",
  overlay: "rgba(0, 0, 0, 0.6)",
  shadow: "#000000",
};

export const palettes = { light, dark };

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 } as const;
/** Touch targets: 48 dp minimum, larger for the inputs operators use all shift */
export const size = { touch: 48, button: 52, input: 52, scan: 60 } as const;

const tabular: TextStyle = { fontVariant: ["tabular-nums"] };

/** Inputs show focus with their own border; drop the browser's outline in the web build */
export const noWebOutline: TextStyle = Platform.OS === "web" ? { outlineWidth: 0, outlineStyle: "solid" } : {};

export const type = {
  display: { fontSize: 34, fontWeight: "700", letterSpacing: -0.5, ...tabular },
  title: { fontSize: 20, fontWeight: "700", letterSpacing: -0.2 },
  heading: { fontSize: 17, fontWeight: "600" },
  body: { fontSize: 16 },
  label: { fontSize: 14, fontWeight: "500" },
  caption: { fontSize: 13 },
  overline: { fontSize: 12, fontWeight: "600", letterSpacing: 0.6, textTransform: "uppercase" },
  qty: { fontSize: 16, fontWeight: "600", ...tabular },
} satisfies Record<string, TextStyle>;

export type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "info";

/** Fill, text-safe foreground and tint for a status tone */
export function tone(c: Palette, t: Tone): { fill: string; text: string; tint: string } {
  switch (t) {
    case "primary":
      return { fill: c.primary, text: c.primaryText, tint: c.primaryTint };
    case "success":
      return { fill: c.success, text: c.successText, tint: c.successTint };
    case "warning":
      return { fill: c.warning, text: c.warningText, tint: c.warningTint };
    case "danger":
      return { fill: c.danger, text: c.dangerText, tint: c.dangerTint };
    case "info":
      return { fill: c.info, text: c.infoText, tint: c.infoTint };
    default:
      return { fill: c.textMuted, text: c.textSecondary, tint: c.surfaceAlt };
  }
}

/** The active palette: the theme setting on Home ("system" follows the device) */
export function useTheme(): { c: Palette; dark: boolean } {
  const pref = useSettings((s) => s.theme);
  const system = useColorScheme();
  const isDark = pref === "dark" || (pref === "system" && system === "dark");
  return { c: isDark ? dark : light, dark: isDark };
}

/** StyleSheet-like styles that follow the theme; rebuilt only when the palette changes */
export function useStyles<T>(factory: (c: Palette) => T): T {
  const { c } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- factories are module-level constants
  return useMemo(() => factory(c), [c]);
}
