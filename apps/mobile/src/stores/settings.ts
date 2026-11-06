import { create } from "zustand";
import { persist } from "zustand/middleware";

import { zustandStorage } from "@/lib/storage";

interface SettingsState {
  /**
   * Continuous scanning: every scan of an item counts as 1 (goods labelled per unit), instead of opening the quantity
   * panel. Items that need a batch or expiry date typed in still open it. A device setting: it fits the goods, not the user.
   */
  eachScanCountsOne: boolean;
  setEachScanCountsOne: (on: boolean) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      eachScanCountsOne: false,
      setEachScanCountsOne: (eachScanCountsOne) => set({ eachScanCountsOne }),
    }),
    { name: "wms.settings", storage: zustandStorage },
  ),
);
