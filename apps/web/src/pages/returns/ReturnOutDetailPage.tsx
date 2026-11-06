import SimpleDocDetail from "@/components/SimpleDocDetail";
import { formatQty } from "@/components/ui";

export default function ReturnOutDetailPage() {
  return (
    <SimpleDocDetail
      path="returns-out"
      docLabel="Return to supplier"
      permPrefix="return_out"
      partnerLabel="Supplier"
      refPath="purchase-orders"
      postConfirm="Have the goods been handed to the supplier? Posting deducts them from the source location."
      columns={[
        { title: "Quantity", dataIndex: "qty_actual", align: "right", render: formatQty },
        { title: "From location", render: (_, l) => <span className="wms-mono">{l.from_location?.code}</span> },
        { title: "Batch no.", dataIndex: "batch_no" },
        { title: "Expiry date", dataIndex: "expiry_date" },
      ]}
    />
  );
}
