import Constants from "expo-constants";
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { zustandStorage } from "@/lib/storage";

const DEFAULT_SERVER_URL =
  (Constants.expoConfig?.extra?.defaultServerUrl as string | undefined) ?? "http://localhost:8000/api/v1";

interface SessionState {
  serverUrl: string;
  token: string | null;
  username: string | null;
  setServerUrl: (url: string) => void;
  setLogin: (token: string, username: string) => void;
  logout: () => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      serverUrl: DEFAULT_SERVER_URL,
      token: null,
      username: null,
      setServerUrl: (serverUrl) => set({ serverUrl: serverUrl.trim() }),
      setLogin: (token, username) => set({ token, username }),
      logout: () => set({ token: null }),
    }),
    { name: "wms.session", storage: zustandStorage },
  ),
);
