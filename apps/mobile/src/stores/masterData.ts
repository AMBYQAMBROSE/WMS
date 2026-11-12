import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";

import { request } from "@/lib/api";
import { gtinCandidates, parseGs1 } from "@/lib/gs1";
import { loadLarge, saveLarge } from "@/lib/largeStore";
import type { MasterData, MobileItem, MobileLocation } from "@/lib/types";

export interface ItemMatch {
  item: MobileItem;
  uomId: string;
  /** From a GS1 code or our stock label: what the goods themselves say, so it is not typed */
  lot?: { batchNo: string | null; expiryDate: string | null; qty: number | null };
}

/** Server compact format (columnar, units by index); see backend /mobile/master-data?format=compact */
interface CompactTable {
  fields: string[];
  rows: unknown[][];
}
interface CompactMasterData {
  format: "compact";
  generated_at: string;
  uoms: MasterData["uoms"];
  items: CompactTable;
  barcodes: CompactTable;
  conversions: CompactTable;
  locations: CompactTable;
}

interface Indexes {
  itemsById: Map<string, MobileItem>;
  barcodes: Map<string, ItemMatch>;
  skus: Map<string, MobileItem>;
  locations: Map<string, MobileLocation>;
}

interface MasterDataState {
  data: MasterData | null;
  indexes: Indexes | null;
  /** Local cache has been read (whether or not there was data) */
  hydrated: boolean;
  refresh: () => Promise<void>;
  hydrate: () => Promise<void>;
  findItem: (code: string) => ItemMatch | null;
  findLocation: (code: string) => MobileLocation | null;
  /** How many base units one unit of uomId is for the item (a carton barcode counts its pack size); null if unknown */
  baseFactor: (item: MobileItem, uomId: string) => number | null;
}

const STORAGE_KEY = "wms.masterData.v2";
// Older versions stored it whole in AsyncStorage; delete it after upgrading to free space
const LEGACY_KEY = "wms.masterData";

function decode(c: CompactMasterData): MasterData {
  const table = (t: CompactTable) =>
    t.rows.map((row) => Object.fromEntries(t.fields.map((f, i) => [f, row[i]])) as Record<string, unknown>);
  const uomId = (index: unknown) => c.uoms[index as number]?.id ?? "";
  return {
    generated_at: c.generated_at.replace(/Z$/, ""),
    uoms: c.uoms,
    items: table(c.items).map((i) => ({
      id: i.id as string,
      sku_code: i.sku_code as string,
      name: i.name as string,
      barcode: (i.barcode as string | null) ?? null,
      base_uom_id: uomId(i.base_uom_id),
      is_batch_managed: !!i.is_batch_managed,
      is_expiry_managed: !!i.is_expiry_managed,
    })),
    barcodes: table(c.barcodes).map((b) => ({ barcode: b.barcode as string, item_id: b.item_id as string, uom_id: uomId(b.uom_id) })),
    conversions: table(c.conversions).map((v) => ({
      item_id: v.item_id as string,
      from_uom_id: uomId(v.from_uom_id),
      to_uom_id: uomId(v.to_uom_id),
      factor: v.factor as number,
    })),
    locations: table(c.locations).map((l) => ({
      id: l.id as string,
      code: l.code as string,
      name: l.name as string,
      location_type: l.location_type as string,
      is_locked: !!l.is_locked,
    })),
  };
}

/** Indexes for scan lookup: comparing one by one is too slow with tens of thousands of items, so build maps by barcode / SKU / location code */
function buildIndexes(data: MasterData): Indexes {
  const itemsById = new Map(data.items.map((i) => [i.id, i]));
  const barcodes = new Map<string, ItemMatch>();
  // Lookup order: the multi-barcode table (with pack unit) before the item's main barcode
  for (const i of data.items) if (i.barcode) barcodes.set(i.barcode, { item: i, uomId: i.base_uom_id });
  for (const b of data.barcodes) {
    const item = itemsById.get(b.item_id);
    if (item) barcodes.set(b.barcode, { item, uomId: b.uom_id });
  }
  return {
    itemsById,
    barcodes,
    skus: new Map(data.items.map((i) => [i.sku_code.toUpperCase(), i])),
    locations: new Map(data.locations.map((l) => [l.code.toUpperCase(), l])),
  };
}

export const useMasterData = create<MasterDataState>()((set, get) => ({
  data: null,
  indexes: null,
  hydrated: false,
  refresh: async () => {
    const compact = await request<CompactMasterData>("GET", "/mobile/master-data?format=compact");
    const data = decode(compact);
    set({ data, indexes: buildIndexes(data) });
    await saveLarge(STORAGE_KEY, JSON.stringify(compact));
  },
  hydrate: async () => {
    void AsyncStorage.removeItem(LEGACY_KEY).catch(() => undefined);
    try {
      const text = await loadLarge(STORAGE_KEY);
      if (text && !get().data) {
        const data = decode(JSON.parse(text) as CompactMasterData);
        set({ data, indexes: buildIndexes(data) });
      }
    } catch {
      // Local cache corrupted: wait for the next online refresh
    } finally {
      set({ hydrated: true });
    }
  },
  // Lookup order: barcode (multi-barcode table -> item main barcode) -> SKU code -> GS1 code / stock label
  findItem: (raw) => {
    const code = raw.trim();
    const idx = get().indexes;
    if (!idx || !code) return null;
    const plain = (value: string): ItemMatch | null => {
      const byBarcode = idx.barcodes.get(value);
      if (byBarcode) return byBarcode;
      const item = idx.skus.get(value.toUpperCase());
      return item ? { item, uomId: item.base_uom_id } : null;
    };
    const direct = plain(code);
    if (direct) return direct;
    const gs1 = parseGs1(raw);
    if (!gs1) return null;
    const keys = [...(gs1.itemCode ? [gs1.itemCode] : []), ...(gs1.gtin ? gtinCandidates(gs1.gtin) : [])];
    for (const key of keys) {
      const match = plain(key);
      if (match) return { ...match, lot: { batchNo: gs1.batch, expiryDate: gs1.expiry, qty: gs1.qty } };
    }
    return null;
  },
  findLocation: (raw) => get().indexes?.locations.get(raw.trim().toUpperCase()) ?? null,
  baseFactor: (item, uomId) => {
    if (uomId === item.base_uom_id) return 1;
    const conversions = get().data?.conversions ?? [];
    const direct = conversions.find((v) => v.item_id === item.id && v.from_uom_id === uomId && v.to_uom_id === item.base_uom_id);
    if (direct) return direct.factor;
    const inverse = conversions.find((v) => v.item_id === item.id && v.from_uom_id === item.base_uom_id && v.to_uom_id === uomId);
    return inverse && inverse.factor ? 1 / inverse.factor : null;
  },
}));

// On startup, load the last downloaded master data from local storage (barcodes resolve even offline)
void useMasterData.getState().hydrate();
