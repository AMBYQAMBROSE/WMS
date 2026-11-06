import { theme, type ThemeConfig } from "antd";

export type ColorMode = "light" | "dark";
/** What the user picked; "system" follows the operating system setting */
export type ThemePreference = ColorMode | "system";
export type Density = "comfortable" | "compact";

/**
 * Design tokens. One neutral scale per mode plus a single indigo accent; status colors live in global.css as CSS variables
 * (--wms-tone-*) so they can be tuned per mode without touching components. antd components read the values below.
 */
export const PALETTE = {
  light: {
    primary: "#4f46e5",
    bgLayout: "#f7f8fa",
    bgSider: "#fbfbfc",
    bgContainer: "#ffffff",
    bgElevated: "#ffffff",
    bgSubtle: "#f9fafb",
    bgHover: "#f3f4f6",
    border: "#e4e6eb",
    borderSubtle: "#eef0f3",
    text: "#0f1115",
    textSecondary: "#545a66",
    textTertiary: "#7d8390",
    textQuaternary: "#a9aeb8",
    success: "#15803d",
    warning: "#b45309",
    error: "#dc2626",
    info: "#2563eb",
  },
  dark: {
    primary: "#6d6ff5",
    bgLayout: "#0e0f12",
    bgSider: "#111215",
    bgContainer: "#16171b",
    bgElevated: "#1c1d22",
    bgSubtle: "#191a1f",
    bgHover: "#202127",
    border: "#2a2c33",
    borderSubtle: "#222329",
    text: "#ecedef",
    textSecondary: "#a4a8b1",
    textTertiary: "#7b808a",
    textQuaternary: "#585c65",
    success: "#22c55e",
    warning: "#f59e0b",
    error: "#f05252",
    info: "#4f8ff7",
  },
} as const;

/** Kept for existing imports: the light-mode brand values */
export const BRAND = {
  primary: PALETTE.light.primary,
  success: PALETTE.light.success,
  warning: PALETTE.light.warning,
  error: PALETTE.light.error,
  info: PALETTE.light.info,
};

export const FONT_FAMILY =
  "'Inter Variable', Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

export const MONO_FAMILY = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

/** Shell dimensions, shared by the layout and the CSS (sticky table headers sit under the top bar) */
export const SHELL = {
  headerHeight: 56,
  siderWidth: 248,
  siderCollapsedWidth: 64,
};

const prefersReducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function buildTheme(mode: ColorMode, density: Density = "comfortable"): ThemeConfig {
  const dark = mode === "dark";
  const p = PALETTE[mode];
  const compact = density === "compact";
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    cssVar: {},
    hashed: false,
    token: {
      colorPrimary: p.primary,
      colorSuccess: p.success,
      colorWarning: p.warning,
      colorError: p.error,
      colorInfo: p.info,
      colorLink: p.primary,
      colorBgLayout: p.bgLayout,
      colorBgContainer: p.bgContainer,
      colorBgElevated: p.bgElevated,
      colorBorder: p.border,
      colorBorderSecondary: p.borderSubtle,
      colorText: p.text,
      colorTextSecondary: p.textSecondary,
      colorTextTertiary: p.textTertiary,
      colorTextQuaternary: p.textQuaternary,
      colorFillQuaternary: dark ? "rgba(255,255,255,0.03)" : "rgba(15,17,21,0.025)",
      fontFamily: FONT_FAMILY,
      fontFamilyCode: MONO_FAMILY,
      fontSize: 14,
      lineHeight: 1.5,
      borderRadius: 8,
      borderRadiusLG: 10,
      borderRadiusSM: 6,
      borderRadiusXS: 4,
      controlHeight: 34,
      controlHeightSM: 26,
      controlHeightLG: 40,
      boxShadow: dark
        ? "0 0 0 1px rgba(255,255,255,0.04), 0 8px 24px rgba(0,0,0,0.5)"
        : "0 0 0 1px rgba(15,17,21,0.04), 0 4px 12px rgba(15,17,21,0.06), 0 12px 32px -8px rgba(15,17,21,0.10)",
      boxShadowSecondary: dark
        ? "0 0 0 1px rgba(255,255,255,0.05), 0 12px 32px rgba(0,0,0,0.55)"
        : "0 0 0 1px rgba(15,17,21,0.05), 0 8px 16px -4px rgba(15,17,21,0.08), 0 20px 40px -8px rgba(15,17,21,0.14)",
      motion: !prefersReducedMotion(),
      motionDurationFast: "0.12s",
      motionDurationMid: "0.18s",
      motionDurationSlow: "0.24s",
      wireframe: false,
    },
    components: {
      Layout: {
        siderBg: p.bgSider,
        headerBg: "transparent",
        headerHeight: SHELL.headerHeight,
        headerPadding: "0 20px",
        bodyBg: p.bgLayout,
      },
      Menu: {
        itemBg: "transparent",
        subMenuItemBg: "transparent",
        itemColor: p.textSecondary,
        itemHoverColor: p.text,
        itemHoverBg: p.bgHover,
        itemActiveBg: p.bgHover,
        itemSelectedBg: dark ? "rgba(109,111,245,0.16)" : "rgba(79,70,229,0.08)",
        itemSelectedColor: dark ? "#c7c8ff" : p.primary,
        groupTitleColor: p.textTertiary,
        popupBg: p.bgElevated,
        itemHeight: 32,
        itemBorderRadius: 6,
        itemMarginInline: 8,
        itemMarginBlock: 1,
        subMenuItemBorderRadius: 6,
        iconSize: 16,
        collapsedIconSize: 16,
        iconMarginInlineEnd: 10,
        fontSize: 13.5,
        activeBarBorderWidth: 0,
      },
      Card: {
        headerFontSize: 14,
        headerHeight: 52,
        headerHeightSM: 42,
        paddingLG: 20,
      },
      Table: {
        headerBg: p.bgSubtle,
        headerColor: p.textTertiary,
        headerSplitColor: "transparent",
        headerSortActiveBg: p.bgHover,
        headerSortHoverBg: p.bgHover,
        rowHoverBg: dark ? "#1b1c21" : "#f8f9fb",
        rowSelectedBg: dark ? "rgba(109,111,245,0.10)" : "rgba(79,70,229,0.05)",
        rowSelectedHoverBg: dark ? "rgba(109,111,245,0.14)" : "rgba(79,70,229,0.08)",
        borderColor: p.borderSubtle,
        cellPaddingBlock: compact ? 7 : 11,
        cellPaddingInline: compact ? 12 : 16,
        cellPaddingBlockMD: compact ? 6 : 9,
        cellPaddingBlockSM: compact ? 5 : 7,
        cellPaddingInlineMD: compact ? 12 : 16,
        cellPaddingInlineSM: compact ? 10 : 14,
        cellFontSize: compact ? 13 : 14,
        headerBorderRadius: 0,
        footerBg: p.bgSubtle,
      },
      Button: {
        fontWeight: 500,
        primaryShadow: "none",
        defaultShadow: "none",
        dangerShadow: "none",
        paddingInline: 14,
      },
      Input: {
        activeShadow: dark ? "0 0 0 3px rgba(109,111,245,0.22)" : "0 0 0 3px rgba(79,70,229,0.12)",
      },
      Select: {
        optionSelectedBg: dark ? "rgba(109,111,245,0.16)" : "rgba(79,70,229,0.07)",
      },
      Tag: {
        defaultBg: p.bgHover,
        defaultColor: p.textSecondary,
      },
      Segmented: {
        itemSelectedBg: dark ? "#2a2c33" : "#ffffff",
        trackBg: dark ? "#111215" : "#eef0f3",
        trackPadding: 3,
      },
      Descriptions: {
        labelBg: p.bgSubtle,
        itemPaddingBottom: 14,
        colonMarginRight: 0,
        colonMarginLeft: 0,
      },
      Modal: {
        titleFontSize: 16,
        contentBg: p.bgElevated,
        headerBg: p.bgElevated,
        footerBg: p.bgElevated,
      },
      Drawer: {
        colorBgElevated: p.bgElevated,
      },
      Statistic: {
        contentFontSize: 24,
      },
      Tabs: {
        titleFontSize: 14,
        horizontalItemPadding: "12px 2px",
        horizontalItemGutter: 24,
        inkBarColor: p.primary,
      },
      Breadcrumb: {
        itemColor: p.textTertiary,
        lastItemColor: p.text,
        linkColor: p.textTertiary,
        linkHoverColor: p.text,
        separatorColor: p.textQuaternary,
        fontSize: 13,
      },
      Tooltip: {
        colorBgSpotlight: dark ? "#2a2c33" : "#16171b",
      },
      Progress: {
        defaultColor: p.primary,
        remainingColor: dark ? "rgba(255,255,255,0.08)" : "rgba(15,17,21,0.06)",
      },
      Alert: {
        withDescriptionPadding: "14px 16px",
      },
    },
  };
}

/**
 * Tones for icons, stat cards and status pills. Values are CSS variables (defined per mode in global.css), so one
 * component renders correctly in light and dark without reading the current mode.
 */
const tone = (name: string) => ({ fg: `var(--wms-tone-${name}-fg)`, bg: `var(--wms-tone-${name}-bg)` });
export const ACCENTS = {
  indigo: tone("indigo"),
  cyan: tone("cyan"),
  green: tone("green"),
  amber: tone("amber"),
  red: tone("red"),
  violet: tone("violet"),
  blue: tone("blue"),
  slate: tone("slate"),
} as const;
export type Accent = keyof typeof ACCENTS;
