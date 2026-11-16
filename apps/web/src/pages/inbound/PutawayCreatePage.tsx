import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import TransferForm from "@/components/TransferForm";
import { useDocument } from "@/components/documents";
import { DetailSkeleton } from "@/components/ui";

export default function PutawayCreatePage() {
  const [searchParams] = useSearchParams();
  const grnId = searchParams.get("grn") ?? undefined;
  const { data: grn, isLoading } = useDocument("grns", grnId);

  // What earlier putaways of this receipt left over, so a receipt that is already put away is not offered again
  const { data: remaining, isLoading: remainingLoading } = useQuery({
    queryKey: ["grns", grnId, "putaway-remaining"],
    queryFn: async () =>
      (await apiClient.get<{ line_id: string; qty: number }[]>(`/grns/${grnId}/putaway-remaining`)).data,
    enabled: !!grnId,
    staleTime: 0,
    gcTime: 0,
  });

  if (grnId && (isLoading || remainingLoading)) return <DetailSkeleton />;
  return (
    <TransferForm
      path="putaways"
      docLabel="Putaway"
      targetTypes={["BIN"]}
      targetLabel="Target bin"
      sourceGrn={grn}
      remaining={remaining && Object.fromEntries(remaining.map((r) => [r.line_id, r.qty]))}
    />
  );
}
