import { create } from "zustand";
import { persist } from "zustand/middleware";

import { zustandStorage } from "@/lib/storage";

export type ThemePreference = "system" | "light" | "dark";

interface SettingsState {
  /**
   * Continuous scanning: every scan of an item counts as 1 (goods labelled per unit), instead of opening the quantity
   * panel. Items that need a batch or expiry date typed in still open it. A device setting: it fits the goods, not the user.
   */
  eachScanCountsOne: boolean;
  setEachScanCountsOne: (on: boolean) => void;
  /** Light / dark / follow the device (night shifts and cold stores prefer dark) */
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      eachScanCountsOne: false,
      setEachScanCountsOne: (eachScanCountsOne) => set({ eachScanCountsOne }),
      theme: "system",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "wms.settings", storage: zustandStorage },
  ),
);
