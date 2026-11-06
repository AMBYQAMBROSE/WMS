/**
 * Live updates: the backend streams "what changed" (server-sent events, app/api/v1/events.py) and we refetch the
 * affected queries, so lists, stock and the dashboard follow what other users and PDAs do without reloading.
 *
 * One stream per browser, not per tab: browsers allow about 6 HTTP/1.1 connections per site, and a stream per tab
 * would starve normal requests once a few tabs are open. Tabs elect a leader with a lease in localStorage (the Web
 * Locks API needs HTTPS, which on-prem installs often lack); the leader holds the stream and relays every batch to
 * the other tabs over a BroadcastChannel.
 */
import { useEffect } from "react";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { create } from "zustand";

import { DOC_PATHS } from "@/constants/labels";
import { useAuthStore } from "@/stores/authStore";

export type LiveStatus = "connecting" | "live" | "offline";

export interface ChangeEvent {
  type: string;
  id?: string;
  parent_id?: string | null;
  action?: string;
  doc_type?: string | null;
}

export const useLiveStore = create<{ status: LiveStatus; setStatus: (s: LiveStatus) => void }>((set) => ({
  status: "connecting",
  setStatus: (status) => set({ status }),
}));

const LEASE_KEY = "wms-live-leader";
const LEASE_MS = 10_000;
const RENEW_MS = 3_000;
const DEBOUNCE_MS = 400;
// Report-type data (dashboard, reports, system health) is cached on the server for REPORT_CACHE_SECONDS = 10
// (app/services/report_service.py). Refreshing it this long after a change guarantees numbers computed after the change,
// and caps the cost at one refetch per window however busy the warehouse is. Must stay above the server's cache time.
const REPORT_REFRESH_DELAY_MS = 11_000;
const SLOW_KEYS = new Set(["reports", "system-status"]);
const TAB_ID = Math.random().toString(36).slice(2);

type Message = { kind: "events"; events: ChangeEvent[] } | { kind: "status"; status: LiveStatus };

/** Query keys (first segment) to refetch per kind of change; documents also move stock and the dashboard */
const MASTER_KEYS: Record<string, string[]> = {
  item: ["items"],
  item_barcode: ["items"],
  item_uom_conversion: ["items"],
  location: ["locations", "reports"],
  business_partner: ["business-partners"],
  uom: ["uoms"],
  reason_code: ["reason-codes"],
  user: ["users"],
  role: ["roles", "me"],
  feature_flag: ["features", "me"],
  tenant: ["me"],
  integration_connector: ["integration"],
  returnable_asset_type: ["returnable-assets"],
  returnable_asset_txn: ["returnable-assets"],
};
const DOCUMENT_TYPES = new Set(["document", "document_line", "shipment_info", "count_entry"]);
// Documents whose posting changes the progress shown on their source order
const RELATED: Record<string, string[]> = {
  GRN: ["purchase-orders", "putaways"],
  PUTAWAY: ["grns"],
  PICK: ["sales-orders", "shipments"],
  SHIP: ["sales-orders", "picks"],
  SO: ["picks", "shipments"],
  RETURN_IN: ["sales-orders"],
  RETURN_OUT: ["purchase-orders"],
};

export function keysFor(events: ChangeEvent[]): Set<string> | "all" {
  const keys = new Set<string>(["audit-logs", "system-status"]);
  for (const e of events) {
    if (e.type === "resync") return "all";
    if (DOCUMENT_TYPES.has(e.type)) {
      const path = e.doc_type ? DOC_PATHS[e.doc_type] : undefined;
      if (path) keys.add(path);
      for (const k of RELATED[e.doc_type ?? ""] ?? []) keys.add(k);
      ["stock", "reports"].forEach((k) => keys.add(k));
    } else {
      for (const k of MASTER_KEYS[e.type] ?? []) keys.add(k);
    }
  }
  return keys;
}

function createRefresher(queryClient: QueryClient) {
  let pending: ChangeEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;

  // Slow keys: one refresh REPORT_REFRESH_DELAY_MS after the first change; changes made while it waits get one more
  // refresh after the last of them, so the final state always shows
  const slowDue = new Set<string>();
  let slowTimer: ReturnType<typeof setTimeout> | undefined;
  let lastSlowChange = 0;
  let slowScheduledAt = 0;
  const scheduleSlow = (delay: number) => {
    slowScheduledAt = Date.now();
    slowTimer = setTimeout(() => {
      slowTimer = undefined;
      slowDue.forEach((key) => void queryClient.invalidateQueries({ queryKey: [key] }));
      if (lastSlowChange > slowScheduledAt) scheduleSlow(lastSlowChange + REPORT_REFRESH_DELAY_MS - Date.now());
      else slowDue.clear();
    }, Math.max(0, delay));
  };

  return (events: ChangeEvent[]) => {
    pending.push(...events);
    clearTimeout(timer);
    // Bursts (posting a document touches many rows, a PDA scans quickly) become one round of refetches
    timer = setTimeout(() => {
      const keys = keysFor(pending);
      pending = [];
      if (keys === "all") {
        void queryClient.invalidateQueries();
        return;
      }
      keys.forEach((key) => {
        if (!SLOW_KEYS.has(key)) {
          void queryClient.invalidateQueries({ queryKey: [key] });
          return;
        }
        slowDue.add(key);
        lastSlowChange = Date.now();
      });
      if (slowDue.size && !slowTimer) scheduleSlow(REPORT_REFRESH_DELAY_MS);
    }, DEBOUNCE_MS);
  };
}

function readLease(): { tab: string; until: number } | null {
  try {
    return JSON.parse(localStorage.getItem(LEASE_KEY) ?? "null");
  } catch {
    return null;
  }
}

/** Parse "event:"/"data:" blocks out of the SSE byte stream */
async function readStream(response: Response, onEvent: (event: string, data: string) => void, signal: AbortSignal) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (data.length) onEvent(event, data.join("\n"));
    }
  }
}

/** Mount once, in the signed-in layout */
export function useLiveUpdates() {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const setStatus = useLiveStore((s) => s.setStatus);

  useEffect(() => {
    if (!token) return;
    const refresh = createRefresher(queryClient);
    const channel = "BroadcastChannel" in window ? new BroadcastChannel("wms-live") : null;
    let leading = false;
    let stopped = false;
    let controller: AbortController | undefined;

    const publish = (message: Message) => {
      if (message.kind === "events") refresh(message.events);
      else setStatus(message.status);
      channel?.postMessage(message);
    };
    if (channel) {
      channel.onmessage = (e: MessageEvent<Message>) => {
        if (e.data.kind === "events") refresh(e.data.events);
        else setStatus(e.data.status);
      };
    }

    const stream = async () => {
      let attempt = 0;
      let connectedBefore = false;
      while (leading && !stopped) {
        controller = new AbortController();
        try {
          publish({ kind: "status", status: "connecting" });
          const response = await fetch("/api/v1/events/stream", {
            headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
            signal: controller.signal,
          });
          if (response.status === 401) {
            publish({ kind: "status", status: "offline" });
            return; // signed out or expired: normal requests take care of sending the user to sign in
          }
          if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
          await readStream(
            response,
            (event, data) => {
              if (event === "ready") {
                attempt = 0;
                publish({ kind: "status", status: "live" });
                // Changes made while we were reconnecting were not streamed: refetch what is on screen
                if (connectedBefore) publish({ kind: "events", events: [{ type: "resync" }] });
                connectedBefore = true;
              } else {
                publish({ kind: "events", events: JSON.parse(data) as ChangeEvent[] });
              }
            },
            controller.signal,
          );
          // The server ends streams after a while; reconnect right away
        } catch {
          if (stopped || !leading) return;
          publish({ kind: "status", status: "offline" });
          attempt += 1;
          await new Promise((r) => setTimeout(r, Math.min(30_000, 1_000 * 2 ** attempt)));
        }
      }
    };

    // Leader election: renew our lease, or take over one that expired (its tab was closed or put to sleep)
    const tick = () => {
      if (stopped) return;
      const lease = readLease();
      const now = Date.now();
      if (!lease || lease.tab === TAB_ID || lease.until < now) {
        localStorage.setItem(LEASE_KEY, JSON.stringify({ tab: TAB_ID, until: now + LEASE_MS }));
        if (!leading && readLease()?.tab === TAB_ID) {
          leading = true;
          void stream();
        } else if (leading) {
          // Tabs opened since the last change of status learn it here
          channel?.postMessage({ kind: "status", status: useLiveStore.getState().status } satisfies Message);
        }
      } else if (leading) {
        // Another tab won a race for the lease: let it stream
        leading = false;
        controller?.abort();
      }
    };
    tick();
    const interval = setInterval(tick, RENEW_MS);
    const release = () => {
      if (readLease()?.tab === TAB_ID) localStorage.removeItem(LEASE_KEY);
    };
    window.addEventListener("beforeunload", release);

    return () => {
      stopped = true;
      leading = false;
      clearInterval(interval);
      controller?.abort();
      release();
      window.removeEventListener("beforeunload", release);
      channel?.close();
    };
  }, [token, queryClient, setStatus]);
}
