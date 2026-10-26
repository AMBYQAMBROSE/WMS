import { useQuery } from "@tanstack/react-query";
import { Select } from "antd";
import type { SelectProps } from "antd";

import { apiClient } from "@/api/client";
import type { BusinessPartner, Item, Location, UomBrief } from "@/api/types";

type Props = Omit<SelectProps, "options" | "loading">;

// 下拉数据一次取 500 条在前端过滤，主数据量上来后再改成服务端搜索
function useList<T>(key: string, path: string) {
  return useQuery({
    queryKey: [key, "options"],
    queryFn: async () => (await apiClient.get<T[]>(path, { params: { limit: 500 } })).data,
  });
}

export function useItems() {
  return useList<Item>("items", "/items");
}

export function useUoms() {
  return useList<UomBrief>("uoms", "/uoms");
}

export function useLocations() {
  return useList<Location>("locations", "/locations");
}

export function SupplierSelect(props: Props) {
  const { data, isLoading } = useList<BusinessPartner>("business-partners", "/business-partners");
  const options = (data ?? [])
    .filter((p) => p.is_active && p.partner_type !== "customer")
    .map((p) => ({ value: p.id, label: `${p.code} ${p.name}` }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} {...props} />;
}

export function ItemSelect(props: Props) {
  const { data, isLoading } = useItems();
  const options = (data ?? [])
    .filter((i) => i.is_active)
    .map((i) => ({ value: i.id, label: `${i.sku_code} ${i.name}` }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} {...props} />;
}

export function UomSelect(props: Props) {
  const { data, isLoading } = useUoms();
  const options = (data ?? []).map((u) => ({ value: u.id, label: `${u.code} ${u.name}` }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} {...props} />;
}

export function LocationSelect({ types, ...props }: Props & { types?: string[] }) {
  const { data, isLoading } = useLocations();
  const options = (data ?? [])
    .filter((l) => l.is_active && (!types || types.includes(l.location_type)))
    .map((l) => ({
      value: l.id,
      label: `${l.code} ${l.name}${l.is_locked ? "（已锁定）" : ""}`,
      disabled: l.is_locked && !!types,
    }));
  return <Select showSearch optionFilterProp="label" loading={isLoading} options={options} {...props} />;
}
