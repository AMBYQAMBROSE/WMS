import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ColorMode, Density, ThemePreference } from "@/theme";

interface UiState {
  /** What the user chose; persisted */
  preference: ThemePreference;
  /** The mode in effect (preference resolved against the operating system); persisted too so index.html can paint the right background before React loads */
  mode: ColorMode;
  density: Density;
  siderCollapsed: boolean;
  /** Decorative animations (entrances, count-ups, theme reveal); the OS "reduce motion" setting overrides it */
  animations: boolean;
  setAnimations: (animations: boolean) => void;
  /** Open the print preview by itself after posting a document (and after allocating, for the pick list) */
  printAfterPosting: boolean;
  setPrintAfterPosting: (printAfterPosting: boolean) => void;
  setPreference: (preference: ThemePreference) => void;
  /** Flip between light and dark (leaves "system") */
  toggleMode: () => void;
  setDensity: (density: Density) => void;
  setSiderCollapsed: (collapsed: boolean) => void;
  /** Called when the operating system switches between light and dark */
  syncSystemMode: () => void;
}

const systemMode = (): ColorMode =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";

const resolve = (preference: ThemePreference): ColorMode => (preference === "system" ? systemMode() : preference);

/** UI preferences (color mode, table density, collapsed navigation), kept per browser */
export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      preference: "system",
      mode: systemMode(),
      density: "comfortable",
      siderCollapsed: false,
      animations: true,
      setAnimations: (animations) => set({ animations }),
      printAfterPosting: true,
      setPrintAfterPosting: (printAfterPosting) => set({ printAfterPosting }),
      setPreference: (preference) => set({ preference, mode: resolve(preference) }),
      toggleMode: () => {
        const preference = get().mode === "dark" ? "light" : "dark";
        set({ preference, mode: preference });
      },
      setDensity: (density) => set({ density }),
      setSiderCollapsed: (siderCollapsed) => set({ siderCollapsed }),
      syncSystemMode: () => {
        if (get().preference === "system") set({ mode: systemMode() });
      },
    }),
    {
      name: "wms-ui",
      version: 1,
      // Version 0 stored only { mode, siderCollapsed }: an explicit choice of light or dark
      migrate: (persisted, version) => {
        const old = (persisted ?? {}) as Partial<UiState>;
        if (version === 0) return { ...old, preference: old.mode ?? "system" } as UiState;
        return old as UiState;
      },
      // The stored mode may be stale when following the system: resolve it again on load
      merge: (persisted, current) => {
        const state = { ...current, ...(persisted as Partial<UiState>) };
        return { ...state, mode: resolve(state.preference) };
      },
    },
  ),
);
