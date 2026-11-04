import SimpleDocDetail from "@/components/SimpleDocDetail";

export default function RepackDetailPage() {
  return (
    <SimpleDocDetail
      path="repacks"
      docLabel="Repack"
      permPrefix="repack"
      postConfirm="Is the work done? Posting deducts the consumed and adds the produced items."
      columns={[
        { title: "Quantity", dataIndex: "qty_actual" },
        { title: "Location", render: (_, l) => (l.from_location ?? l.to_location)?.code },
        { title: "Batch no.", dataIndex: "batch_no" },
        { title: "Expiry date", dataIndex: "expiry_date" },
      ]}
      // Consumption lines only have a from location, output lines only a to location
      lineFilter={(doc) => [
        { title: "Consumed", lines: doc.lines.filter((l) => l.from_location) },
        { title: "Produced", lines: doc.lines.filter((l) => l.to_location) },
      ]}
    />
  );
}
