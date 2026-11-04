import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

export interface Me {
  id: string;
  username: string;
  display_name: string;
  permissions: string[];
  /** Extension features enabled for the tenant (RETURNS / CROSS_DOCK / REPACK / RETURNABLE_ASSET ...) */
  features: string[];
}

export function useMe() {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["me", token],
    queryFn: async () => (await apiClient.get<Me>("/auth/me")).data,
    enabled: !!token,
    staleTime: 60_000,
  });
}

/**
 * Only for showing/hiding UI: menus and buttons the user lacks permission for are hidden instead of failing with 403.
 * The real permission checks happen on every backend endpoint; hiding in the frontend is not security.
 */
export function useCan(): (permission?: string) => boolean {
  const { data } = useMe();
  const granted = new Set(data?.permissions ?? []);
  return (permission?: string) => !permission || granted.has(permission);
}

/** Feature flags: extension modules that are not enabled have no menu entries or buttons (the backend rejects them too) */
export function useFeature(): (feature?: string) => boolean {
  const { data } = useMe();
  const enabled = new Set(data?.features ?? []);
  return (feature?: string) => !feature || enabled.has(feature);
}
