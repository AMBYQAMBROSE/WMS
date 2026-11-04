import { useEffect } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider } from "antd";
import enUS from "antd/locale/en_US";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { EmptyState } from "@/components/ui";
import { useUiStore } from "@/stores/uiStore";
import { buildTheme } from "@/theme";

import "@fontsource-variable/inter";
import "./styles/global.css";

const queryClient = new QueryClient();

function ThemedApp() {
  const mode = useUiStore((s) => s.mode);
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
  }, [mode]);
  return (
    <ConfigProvider locale={enUS} theme={buildTheme(mode)} renderEmpty={() => <EmptyState />}>
      <AntApp>
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
