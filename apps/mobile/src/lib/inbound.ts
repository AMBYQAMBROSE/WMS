import { ApiError, request } from "@/lib/api";
import { loadJson, saveJson } from "@/lib/storage";
import type { CycleCount, Document, DocumentSummary, Pick, StockBalance } from "@/lib/types";

export interface Fetched<T> {
  data: T;
  /** Non-empty means offline data from the local cache; the value is the cache time */
  cachedAt: string | null;
}

/** Online: fetch fresh data and cache it; offline: fall back to the cache so operators can keep working in dead zones */
async function withCache<T>(key: string, load: () => Promise<T>, offlineMessage: string): Promise<Fetched<T>> {
  try {
    const data = await load();
    await saveJson(key, { data, cachedAt: new Date().toISOString() });
    return { data, cachedAt: null };
  } catch (error) {
    if (error instanceof ApiError && error.kind === "network") {
      const cached = await loadJson<{ data: T; cachedAt: string }>(key);
      if (cached) return cached;
      throw new ApiError("network", offlineMessage);
    }
    throw error;
  }
}

export function fetchPurchaseOrder(docNo: string): Promise<Fetched<Document>> {
  const code = docNo.trim();
  return withCache(
    `cache.po.${code.toUpperCase()}`,
    async () => {
      const found = await request<Document[]>("GET", `/purchase-orders?doc_no=${encodeURIComponent(code)}`);
      if (!found.length) throw new ApiError("business", `Purchase order ${code} not found`);
      return request<Document>("GET", `/purchase-orders/${found[0].id}`);
    },
    `Offline and purchase order ${code} is not cached on this device; scan again where there is signal`,
  );
}

export function fetchBalances(locationId: string, locationCode: string): Promise<Fetched<StockBalance[]>> {
  return withCache(
    `cache.balances.${locationId}`,
    () => request<StockBalance[]>("GET", `/stock/balances?location_id=${locationId}&limit=500`),
    `Offline and stock for location ${locationCode} is not cached on this device; scan again where there is signal`,
  );
}

export function fetchActiveCounts(): Promise<Fetched<DocumentSummary[]>> {
  return withCache(
    "cache.counts.active",
    () => request<DocumentSummary[]>("GET", "/cycle-counts?status=COUNTING&limit=100"),
    "Offline and no cycle counts are cached on this device; open again where there is signal",
  );
}

export function fetchCount(id: string, docNo: string): Promise<Fetched<CycleCount>> {
  return withCache(
    `cache.count.${id}`,
    () => request<CycleCount>("GET", `/cycle-counts/${id}`),
    `Offline and cycle count ${docNo} is not cached on this device; open again where there is signal`,
  );
}

export function fetchOpenPicks(): Promise<Fetched<DocumentSummary[]>> {
  return withCache(
    "cache.picks.open",
    () => request<DocumentSummary[]>("GET", "/picks?status=OPEN&limit=100"),
    "Offline and no pick lists are cached on this device; open again where there is signal",
  );
}

export function fetchPick(id: string, docNo: string): Promise<Fetched<Pick>> {
  return withCache(
    `cache.pick.${id}`,
    () => request<Pick>("GET", `/picks/${id}`),
    `Offline and pick list ${docNo} is not cached on this device; open again where there is signal`,
  );
}

export function parseQty(text: string): number | null {
  const value = Number(text.trim());
  if (!Number.isFinite(value) || value <= 0) return null;
  if (!/^\d+(\.\d{1,4})?$/.test(text.trim())) return null;
  return value;
}

export function parseDate(text: string): string | null {
  const value = text.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(value + "T00:00:00Z");
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value) ? value : null;
}

export const fmtQty = (n: number) => String(Math.round(n * 10000) / 10000);
