import SimpleDocDetail from "@/components/SimpleDocDetail";

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
        { title: "Quantity", dataIndex: "qty_actual" },
        { title: "From location", render: (_, l) => l.from_location?.code },
        { title: "Batch no.", dataIndex: "batch_no" },
        { title: "Expiry date", dataIndex: "expiry_date" },
      ]}
    />
  );
}
