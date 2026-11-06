import { Pill, formatQty } from "@/components/ui";

import SimpleDocDetail from "@/components/SimpleDocDetail";

export default function ReturnInDetailPage() {
  return (
    <SimpleDocDetail
      path="returns-in"
      docLabel="Customer return"
      permPrefix="return_in"
      partnerLabel="Customer"
      refPath="sales-orders"
      postConfirm="Have the goods been inspected? Posting adds restock lines to stock; scrap lines are only recorded."
      columns={[
        { title: "Quantity", dataIndex: "qty_actual", align: "right", render: formatQty },
        {
          title: "Disposition",
          render: (_, l) => (l.to_location ? <Pill tone="green" dot>Restock · {l.to_location.code}</Pill> : <Pill tone="red" dot>Scrap</Pill>),
        },
        { title: "Batch no.", dataIndex: "batch_no" },
        { title: "Expiry date", dataIndex: "expiry_date" },
      ]}
    />
  );
}
