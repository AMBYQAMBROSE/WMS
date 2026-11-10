import { useEffect, useMemo, useRef } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider, message } from "antd";
import { isAxiosError } from "axios";
import enUS from "antd/locale/en_US";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { EmptyState } from "@/components/ui";
import { useUiStore } from "@/stores/uiStore";
import { buildTheme } from "@/theme";
import { themeRevealRunning } from "@/theme/motion";

import "@fontsource-variable/inter";
import "./styles/global.css";
import "./styles/motion.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx (not found, no permission, validation) will not change on retry: show the error state at once instead of
      // keeping the user on a loading skeleton for several seconds; network and 5xx errors still retry
      retry: (failureCount, error) => {
        const status = isAxiosError(error) ? error.response?.status : undefined;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 3;
      },
    },
  },
});

// Toasts sit just under the top bar and never pile up
message.config({ top: 64, maxCount: 3, duration: 2.5 });

function ThemedApp() {
  const mode = useUiStore((s) => s.mode);
  const density = useUiStore((s) => s.density);
  const syncSystemMode = useUiStore((s) => s.syncSystemMode);
  const animations = useUiStore((s) => s.animations);
  const first = useRef(true);

  // Follow the operating system while the preference is "system"
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener("change", syncSystemMode);
    return () => media?.removeEventListener("change", syncSystemMode);
  }, [syncSystemMode]);

  useEffect(() => {
    const root = document.documentElement;
    // Cross-fade colors when the user switches mode (not on first paint); global.css skips it under reduced motion
    // (skipped while the circular reveal is drawing the change)
    if (!first.current && !themeRevealRunning) {
      root.classList.add("wms-theme-switching");
      window.setTimeout(() => root.classList.remove("wms-theme-switching"), 320);
    }
    first.current = false;
    root.dataset.theme = mode;
    root.style.colorScheme = mode;
    root.style.background = "";
  }, [mode]);

  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);

  useEffect(() => {
    document.documentElement.dataset.motion = animations ? "on" : "off";
  }, [animations]);

  const themeConfig = useMemo(() => buildTheme(mode, density), [mode, density]);

  // Static message/Modal calls (message.success, Modal.warning) render outside this tree: give them the same theme
  useEffect(() => {
    ConfigProvider.config({
      holderRender: (children) => (
        <ConfigProvider locale={enUS} theme={themeConfig}>
          {children}
        </ConfigProvider>
      ),
    });
  }, [themeConfig]);

  return (
    <ConfigProvider locale={enUS} theme={themeConfig} renderEmpty={() => <EmptyState />}>
      <AntApp message={{ maxCount: 3, top: 64 }}>
        <App />
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemedApp />
    </QueryClientProvider>
  </React.StrictMode>
);
