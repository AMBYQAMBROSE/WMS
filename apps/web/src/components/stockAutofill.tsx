import { useEffect, useState } from "react";

import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { FormInstance } from "antd";
import dayjs from "dayjs";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { Location, StockBalance } from "@/api/types";
import { ItemSelect } from "@/components/selects";

/**
 * Filling a document line from the stock that is actually there, so choosing one thing brings the related fields
 * with it: a location brings its item (and the item's batch, expiry and free quantity), an item brings the one
 * location that holds it. Only unambiguous facts are filled; anything filled can still be changed.
 */

// A bin holds a handful of balances; 500 is the API's page limit
const stockQuery = (filter: { location_id: string } | { item_id: string }) => ({
  queryKey: ["stock", "balances", filter] as const,
  queryFn: async () => (await apiClient.get<StockBalance[]>("/stock/balances", { params: { ...filter, limit: 500 } })).data,
  staleTime: 15_000,
});

const fetchStock = (queryClient: QueryClient, filter: { location_id: string } | { item_id: string }) =>
  queryClient
    .fetchQuery(stockQuery(filter))
    .then((rows) => rows.filter((b) => b.qty_on_hand > 0))
    // No stock information (offline, server error): the user fills the line by hand as before
    .catch(() => [] as StockBalance[]);

const free = (b: StockBalance) => Math.max(b.qty_on_hand - b.qty_allocated, 0);

type LinePath = (string | number)[];

export interface AutofillOptions {
  /** The line's location field; "location_id" unless the line has a from and a to */
  locationField?: string;
  /**
   * The line takes stock out of its location (return to supplier, repack consumption, putaway source): also fill the
   * free quantity, and find the location from the item when only one location holds it.
   */
  source?: boolean;
  /**
   * The location was just changed (not the item). On a source line the new location then decides: an item it does
   * not hold is replaced by what it does hold, and the quantity follows the stock there.
   */
  locationChanged?: boolean;
}

/**
 * Returns `fill(line)`: call it after the line's location or item changed. Needs stock.read; without it nothing is
 * filled and the form works as before.
 */
export function useStockAutofill(form: FormInstance) {
  const queryClient = useQueryClient();
  const can = useCan();

  return async (line: LinePath, { locationField = "location_id", source = false, locationChanged = false }: AutofillOptions = {}) => {
    if (!can("stock.read")) return;
    const get = (field: string) => form.getFieldValue([...line, field]);
    const set = (field: string, value: unknown) => form.setFieldValue([...line, field], value);
    let itemId: string | undefined = get("item_id");
    let locationId: string | undefined = get(locationField);
    let rows: StockBalance[];

    if (locationId) {
      rows = await fetchStock(queryClient, { location_id: locationId });
    } else if (itemId && source) {
      // Item first: when a single location holds it, that is where it comes from
      rows = await fetchStock(queryClient, { item_id: itemId });
      const locations = new Set(rows.map((b) => b.location.id));
      if (locations.size !== 1) return;
      if (get("item_id") !== itemId || get(locationField)) return;
      locationId = rows[0]!.location.id;
      set(locationField, locationId);
    } else {
      return;
    }
    // The user moved on while the stock was loading
    if (get(locationField) !== locationId || get("item_id") !== itemId) return;

    const moved = source && locationChanged;
    if (itemId && moved && rows.length && !rows.some((b) => b.item.id === itemId)) {
      // The line's item is not at the new location: it cannot come from there, so the line starts over
      for (const field of ["item_id", "uom_id", "batch_no", "expiry_date", "qty"]) set(field, undefined);
      itemId = undefined;
    }
    if (itemId) {
      rows = rows.filter((b) => b.item.id === itemId);
    } else {
      if (new Set(rows.map((b) => b.item.id)).size !== 1) return;
      const item = rows[0]!.item;
      set("item_id", item.id);
      set("uom_id", item.base_uom.id);
    }
    // One balance of the item here: its batch and expiry are the only ones the line can mean
    if (rows.length !== 1) return;
    const balance = rows[0]!;
    set("batch_no", balance.batch_no ?? undefined);
    set("expiry_date", balance.expiry_date ? dayjs(balance.expiry_date) : undefined);
    // Quantities on a balance are in the base unit: only fill while the line is in that unit too
    if (source && (moved || !get("qty")) && get("uom_id") === balance.item.base_uom.id && free(balance) > 0) set("qty", free(balance));
  };
}

/**
 * Item dropdown of a line that takes stock out of `locationId`: once the location is chosen it offers only the items
 * stocked there (still searchable). Without a location, or without stock information, every item as usual.
 */
export function StockItemSelect({ locationId, ...props }: React.ComponentProps<typeof ItemSelect> & { locationId?: string }) {
  const can = useCan();
  const { data } = useQuery({ ...stockQuery({ location_id: locationId ?? "" }), enabled: !!locationId && can("stock.read") });
  const ids = locationId && data ? [...new Set(data.filter((b) => b.qty_on_hand > 0).map((b) => b.item.id))] : [];
  // The API takes up to 200 ids; a location with more items than that is searched like any other
  const restrict = ids.length > 0 && ids.length <= 200;
  return (
    <ItemSelect
      {...props}
      stockedIds={restrict ? ids : undefined}
      placeholder={restrict ? `${ids.length} item${ids.length === 1 ? "" : "s"} at this location` : props.placeholder}
    />
  );
}

const key = (name: string) => `wms-last-location:${name}`;

/**
 * The location last used for a purpose on this PC (the receiving dock, the shipping staging area), so forms open with
 * it filled in. It is offered only while it still exists, is active and is not locked.
 * Returns [id, remember]: `id` is undefined until checked; call `remember` when the form is submitted.
 */
export function useLastLocation(name: string): [string | undefined, (id: string | undefined) => void] {
  const queryClient = useQueryClient();
  const [id, setId] = useState<string>();
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(key(name));
    } catch {
      // Storage unavailable (private mode): nothing is remembered
    }
    if (!stored) return;
    let cancelled = false;
    queryClient
      .fetchQuery({
        queryKey: ["locations", "one", stored],
        queryFn: async () => (await apiClient.get<Location>(`/locations/${stored}`)).data,
        staleTime: 5 * 60_000,
      })
      .then((location) => {
        if (!cancelled && location.is_active && !location.is_locked) setId(location.id);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [name, queryClient]);
  const remember = (next: string | undefined) => {
    if (!next) return;
    try {
      localStorage.setItem(key(name), next);
    } catch {
      // See above
    }
  };
  return [id, remember];
}
