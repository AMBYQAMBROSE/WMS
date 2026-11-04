import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ColorMode } from "@/theme";

interface UiState {
  mode: ColorMode;
  siderCollapsed: boolean;
  toggleMode: () => void;
  setSiderCollapsed: (collapsed: boolean) => void;
}

const prefersDark = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;

/** UI preferences (color mode, collapsed navigation), kept per browser */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      mode: prefersDark() ? "dark" : "light",
      siderCollapsed: false,
      toggleMode: () => set((s) => ({ mode: s.mode === "dark" ? "light" : "dark" })),
      setSiderCollapsed: (siderCollapsed) => set({ siderCollapsed }),
    }),
    { name: "wms-ui" },
  ),
);
