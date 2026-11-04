import { theme, type ThemeConfig } from "antd";

export type ColorMode = "light" | "dark";

/** Brand palette. Everything else derives from antd's algorithm so components stay consistent in light and dark. */
export const BRAND = {
  primary: "#4f46e5",
  primaryDeep: "#3730a3",
  accent: "#06b6d4",
  success: "#16a34a",
  warning: "#d97706",
  error: "#dc2626",
  info: "#2563eb",
};

export const FONT_FAMILY =
  "'Inter Variable', Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

export const MONO_FAMILY = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

/** Sider is always dark: it anchors the layout and keeps the navigation readable at a glance */
export const SIDER = {
  bg: "#0f1222",
  bgElevated: "#171a2e",
  border: "rgba(255,255,255,0.06)",
  text: "rgba(226,229,240,0.72)",
  textActive: "#ffffff",
  groupText: "rgba(226,229,240,0.38)",
};

export function buildTheme(mode: ColorMode): ThemeConfig {
  const dark = mode === "dark";
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    cssVar: {},
    hashed: false,
    token: {
      colorPrimary: BRAND.primary,
      colorSuccess: BRAND.success,
      colorWarning: BRAND.warning,
      colorError: BRAND.error,
      colorInfo: BRAND.info,
      colorLink: BRAND.primary,
      colorBgLayout: dark ? "#0b0d17" : "#f4f6fb",
      colorBgContainer: dark ? "#141726" : "#ffffff",
      colorBgElevated: dark ? "#1b1f33" : "#ffffff",
      colorBorder: dark ? "#2a2f48" : "#e3e7ef",
      colorBorderSecondary: dark ? "#232840" : "#edf0f5",
      colorText: dark ? "#e7e9f3" : "#111827",
      colorTextSecondary: dark ? "#a3a9c2" : "#4b5563",
      colorTextTertiary: dark ? "#7c829c" : "#6b7280",
      colorTextQuaternary: dark ? "#5b6079" : "#9ca3af",
      fontFamily: FONT_FAMILY,
      fontFamilyCode: MONO_FAMILY,
      fontSize: 14,
      borderRadius: 8,
      borderRadiusLG: 12,
      borderRadiusSM: 6,
      controlHeight: 36,
      controlHeightSM: 28,
      controlHeightLG: 42,
      boxShadow: dark
        ? "0 8px 24px rgba(0,0,0,0.45)"
        : "0 1px 2px rgba(16,24,40,0.04), 0 8px 24px rgba(16,24,40,0.08)",
      boxShadowSecondary: dark
        ? "0 12px 32px rgba(0,0,0,0.5)"
        : "0 4px 6px -2px rgba(16,24,40,0.05), 0 12px 32px -4px rgba(16,24,40,0.12)",
      wireframe: false,
    },
    components: {
      Layout: {
        siderBg: SIDER.bg,
        headerBg: "transparent",
        headerHeight: 64,
        headerPadding: "0 24px",
        bodyBg: dark ? "#0b0d17" : "#f4f6fb",
      },
      Menu: {
        darkItemBg: SIDER.bg,
        darkSubMenuItemBg: SIDER.bg,
        darkPopupBg: SIDER.bgElevated,
        darkItemColor: SIDER.text,
        darkItemHoverColor: SIDER.textActive,
        darkItemHoverBg: "rgba(255,255,255,0.06)",
        darkItemSelectedBg: BRAND.primary,
        darkItemSelectedColor: "#ffffff",
        darkGroupTitleColor: SIDER.groupText,
        itemHeight: 38,
        itemBorderRadius: 8,
        itemMarginInline: 10,
        subMenuItemBorderRadius: 8,
        iconSize: 16,
        collapsedIconSize: 18,
      },
      Card: {
        headerFontSize: 15,
        headerHeight: 52,
        headerHeightSM: 44,
        paddingLG: 20,
      },
      Table: {
        headerBg: dark ? "#181c2e" : "#f8f9fc",
        headerColor: dark ? "#a3a9c2" : "#4b5563",
        headerSplitColor: "transparent",
        rowHoverBg: dark ? "#1a1e33" : "#f5f6ff",
        borderColor: dark ? "#232840" : "#eef0f5",
        cellPaddingBlock: 12,
        cellPaddingBlockSM: 8,
        headerBorderRadius: 10,
      },
      Button: {
        fontWeight: 500,
        primaryShadow: "0 1px 2px rgba(79,70,229,0.25)",
        defaultShadow: "none",
      },
      Tag: {
        defaultBg: dark ? "#232840" : "#f3f4f6",
      },
      Segmented: {
        itemSelectedBg: dark ? "#2a2f48" : "#ffffff",
        trackBg: dark ? "#0f1222" : "#eef0f5",
      },
      Descriptions: {
        labelBg: dark ? "#181c2e" : "#f8f9fc",
        itemPaddingBottom: 12,
      },
      Modal: {
        titleFontSize: 17,
      },
      Statistic: {
        contentFontSize: 26,
      },
      Tabs: {
        titleFontSize: 14,
        horizontalItemPadding: "12px 4px",
      },
    },
  };
}

/** Accent colors for icons and stat cards; each pairs a strong tone with a soft background */
export const ACCENTS = {
  indigo: { fg: "#4f46e5", bg: "rgba(79,70,229,0.12)" },
  cyan: { fg: "#0891b2", bg: "rgba(8,145,178,0.12)" },
  green: { fg: "#16a34a", bg: "rgba(22,163,74,0.12)" },
  amber: { fg: "#d97706", bg: "rgba(217,119,6,0.14)" },
  red: { fg: "#dc2626", bg: "rgba(220,38,38,0.12)" },
  violet: { fg: "#7c3aed", bg: "rgba(124,58,237,0.12)" },
  blue: { fg: "#2563eb", bg: "rgba(37,99,235,0.12)" },
  slate: { fg: "#64748b", bg: "rgba(100,116,139,0.14)" },
} as const;
export type Accent = keyof typeof ACCENTS;
