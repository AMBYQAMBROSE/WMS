import { useEffect, useState } from "react";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Select } from "antd";
import type { SelectProps } from "antd";

import { apiClient } from "@/api/client";
import type { BusinessPartner, Item, Location, ReasonCode, UomBrief } from "@/api/types";

type Props = Omit<SelectProps, "options" | "loading">;

// Master data (items, locations, partners) can have tens of thousands of rows: dropdowns search on the server as you type, at most 50 results each;
// selected values are fetched separately by ID for display. Records are cached under [resource, "one", id], and pages read item attributes from the same cache.
const SEARCH_LIMIT = 50;
const SEARCH_DELAY_MS = 300;

interface Resource {
  key: string;
  path: string;
}
const ITEMS: Resource = { key: "items", path: "/items" };
const LOCATIONS: Resource = { key: "locations", path: "/locations" };
const PARTNERS: Resource = { key: "business-partners", path: "/business-partners" };

function useDebounced<T>(value: T, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Fetch records by ID (cached). Used to display selected dropdown values and by pages reading batch/expiry settings of selected items */
function useRecords<T extends { id: string }>(resource: Resource, ids: (string | undefined | null)[]): T[] {
  const unique = [...new Set(ids.filter((id): id is string => !!id))];
  const results = useQueries({
    queries: unique.map((id) => ({
      queryKey: [resource.key, "one", id],
      queryFn: async () => (await apiClient.get<T>(`${resource.path}/${id}`)).data,
      staleTime: 5 * 60_000,
    })),
  });
  return results.map((r) => r.data).filter((r): r is T => !!r);
}

export const useItemRecords = (ids: (string | undefined | null)[]) => useRecords<Item>(ITEMS, ids);

function RemoteSelect<T extends { id: string }>({
  resource,
  params,
  toOption,
  onRecordChange,
  value,
  onChange,
  ...props
}: Props & {
  resource: Resource;
  params?: Record<string, unknown>;
  toOption: (record: T) => { value: string; label: string; disabled?: boolean };
  /** Receives the full record after selection (e.g. the item's base unit) */
  onRecordChange?: (record: T | undefined) => void;
}) {
  const queryClient = useQueryClient();
  const [typed, setTyped] = useState("");
  const keyword = useDebounced(typed.trim(), SEARCH_DELAY_MS);
  const search = useQuery({
    queryKey: [resource.key, "search", params, keyword],
    queryFn: async () => {
      const rows = (await apiClient.get<T[]>(resource.path, { params: { ...params, keyword: keyword || undefined, limit: SEARCH_LIMIT, active_only: true } })).data;
      rows.forEach((row) => queryClient.setQueryData([resource.key, "one", row.id], row));
      return rows;
    },
    staleTime: 30_000,
  });
  const selectedIds = (Array.isArray(value) ? value : [value]) as (string | undefined)[];
  const selected = useRecords<T>(resource, selectedIds);
  // Do not show old results while typing or before new results arrive, so Enter never picks an option from the previous search
  const pending = typed.trim() !== keyword || search.isFetching;
  const results = pending ? [] : (search.data ?? []);
  const records = [...results, ...selected.filter((s) => !results.some((r) => r.id === s.id))];
  const [open, setOpen] = useState(false);
  // Barcode scanners type the code and Enter in one burst: remember an Enter pressed before results arrive and pick the first result when they do
  const [enterPending, setEnterPending] = useState(false);

  const choose = (record: T | undefined) => {
    if (!record) return;
    const option = toOption(record);
    onChange?.(option.value, option);
    onRecordChange?.(record);
  };

  useEffect(() => {
    if (enterPending && !pending && keyword) {
      setEnterPending(false);
      const first = results.find((r) => !toOption(r).disabled);
      if (first) {
        choose(first);
        setOpen(false);
        setTyped("");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enterPending, pending, keyword, results]);

  return (
    <Select
      showSearch
      filterOption={false}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setTyped("");
          setEnterPending(false);
        }
      }}
      onSearch={setTyped}
      onInputKeyDown={(e) => {
        if (e.key === "Enter" && pending && typed.trim()) {
          e.preventDefault();
          setEnterPending(true);
        }
      }}
      loading={pending}
      notFoundContent={pending ? "Searching..." : "No matches, try another keyword"}
      options={records.map(toOption)}
      value={value}
      onChange={(next) => {
        const record = records.find((r) => r.id === next);
        if (record) choose(record);
        else onChange?.(next, undefined as never);
      }}
      {...props}
    />
  );
}

const partnerOption = (p: BusinessPartner) => ({ value: p.id, label: `${p.code} ${p.name}` });

export function SupplierSelect(props: Props) {
  return <RemoteSelect<BusinessPartner> resource={PARTNERS} params={{ role: "supplier" }} toOption={partnerOption} {...props} />;
}

export function CustomerSelect(props: Props) {
  return <RemoteSelect<BusinessPartner> resource={PARTNERS} params={{ role: "customer" }} toOption={partnerOption} {...props} />;
}

export function PartnerSelect(props: Props) {
  return <RemoteSelect<BusinessPartner> resource={PARTNERS} toOption={partnerOption} {...props} />;
}

export function ItemSelect(props: Props & { onRecordChange?: (item: Item | undefined) => void }) {
  return (
    <RemoteSelect<Item>
      resource={ITEMS}
      toOption={(i) => ({ value: i.id, label: `${i.sku_code} ${i.name}` })}
      {...props}
    />
  );
}

export function useUoms() {
  return useQuery({
    queryKey: ["uoms", "options"],
    queryFn: async () => (await apiClient.get<UomBrief[]>("/uoms", { params: { limit: 500 } })).data,
  });
}

/** Base units in one of `uomId` for this item: 1 for its base unit, the packing factor for a carton / pallet..., undefined otherwise */
export function unitFactor(item: Item | undefined, uomId: string | undefined): number | undefined {
  if (!item || !uomId) return undefined;
  if (uomId === item.base_uom_id) return 1;
  return item.packings?.find((p) => p.uom.id === uomId)?.factor;
}

/**
 * Unit dropdown. With `item`, only the units that item can be counted in: its base unit and its packing units, each showing
 * how many base units it holds; without one (or while the item loads), every unit.
 */
export function UomSelect({ item, ...props }: Props & { item?: Item }) {
  const { data, isLoading } = useUoms();
  const base = data?.find((u) => u.id === item?.base_uom_id);
  const options =
    item && base
      ? [
          { value: base.id, label: base.code, title: `${base.code} ${base.name} (base unit)` },
          ...(item.packings ?? []).map((p) => ({
            value: p.uom.id,
            label: `${p.uom.code} (${p.factor} ${base.code})`,
            title: `${p.uom.name}: ${p.factor} ${base.code} each`,
          })),
        ]
      : (data ?? []).map((u) => ({ value: u.id, label: `${u.code} ${u.name}` }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} popupMatchSelectWidth={false} {...props} />;
}

/** "= 960 EA" under a quantity entered in a packing unit, so the user sees what goes into or out of stock */
export function BaseQtyHint({ item, uomId, qty }: { item?: Item; uomId?: string; qty?: number | null }) {
  const { data } = useUoms();
  const factor = unitFactor(item, uomId);
  if (!item || !qty || !factor || factor === 1) return null;
  const base = data?.find((u) => u.id === item.base_uom_id)?.code ?? "";
  const total = Math.round(qty * factor * 10000) / 10000;
  return <div className="wms-base-qty">= {total.toLocaleString()} {base}</div>;
}

export function ReasonSelect({ category = "ADJUST", ...props }: Props & { category?: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["reason-codes", "options", category],
    queryFn: async () =>
      (await apiClient.get<ReasonCode[]>("/reason-codes", { params: { category, active_only: true } })).data,
  });
  const options = (data ?? []).map((r) => ({ value: r.id, label: `${r.code} ${r.name}` }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} {...props} />;
}

export function LocationSelect({
  types,
  allowLocked = false,
  ...props
}: Props & { types?: string[]; /** cycle counts may select locked locations */ allowLocked?: boolean }) {
  return (
    <RemoteSelect<Location>
      resource={LOCATIONS}
      params={types ? { types } : undefined}
      toOption={(l) => ({
        value: l.id,
        label: `${l.code} ${l.name}${l.is_locked ? " (locked)" : ""}`,
        disabled: l.is_locked && !!types && !allowLocked,
      })}
      {...props}
    />
  );
}
