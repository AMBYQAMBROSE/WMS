import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";

/**
 * A per-user setting stored on the server (GET/PUT /me/preferences/{key}): it follows the user to any PC, and
 * shared warehouse PCs do not mix users' settings. Saves are optimistic: the UI changes at once.
 *
 * Callers must not save before `loaded`: a save built from the fallback would overwrite what the user has stored.
 */
export function usePreference<T>(key: string, fallback: T): { value: T; loaded: boolean; save: (value: T) => void } {
  const queryClient = useQueryClient();
  const queryKey = ["preferences", key];
  const { data, isSuccess } = useQuery({
    queryKey,
    queryFn: async () => (await apiClient.get<{ value: T | null }>(`/me/preferences/${key}`)).data.value,
    staleTime: Infinity,
  });
  const mutation = useMutation({
    mutationFn: async ({ value }: { value: T; previous: T | null | undefined }) =>
      (await apiClient.put(`/me/preferences/${key}`, { value })).data,
    // Saves of one key run one after another, so the server ends with the last change, not whichever request won a race
    scope: { id: `preferences:${key}` },
    onError: (error, { previous }) => {
      queryClient.setQueryData(queryKey, previous ?? null);
      showError(error);
    },
  });
  // The last value saved from this component: the query cache notifies components on a deferred schedule, so without
  // this a clicked checkbox or star would only change on a later frame (and look unresponsive)
  const [local, setLocal] = useState<{ value: T } | null>(null);
  const save = (value: T) => {
    setLocal({ value });
    // Cancel any load still in flight so it cannot put the old value back
    void queryClient.cancelQueries({ queryKey });
    const previous = queryClient.getQueryData<T | null>(queryKey);
    queryClient.setQueryData(queryKey, value);
    mutation.mutate({ value, previous }, { onError: () => setLocal(null) });
  };
  return { value: local ? local.value : (data ?? fallback), loaded: isSuccess, save };
}
