import { Spin } from "antd";
import { useSearchParams } from "react-router";

import TransferForm from "@/components/TransferForm";
import { useDocument } from "@/components/documents";

export default function PutawayCreatePage() {
  const [searchParams] = useSearchParams();
  const grnId = searchParams.get("grn") ?? undefined;
  const { data: grn, isLoading } = useDocument("grns", grnId);

  if (grnId && isLoading) return <Spin />;
  return (
    <TransferForm path="putaways" docLabel="Putaway" targetTypes={["BIN"]} targetLabel="Target bin" sourceGrn={grn} />
  );
}
