import { Tag } from "antd";

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
        { title: "Quantity", dataIndex: "qty_actual" },
        {
          title: "Disposition",
          render: (_, l) => (l.to_location ? <Tag color="green">Restock {l.to_location.code}</Tag> : <Tag color="red">Scrap</Tag>),
        },
        { title: "Batch no.", dataIndex: "batch_no" },
        { title: "Expiry date", dataIndex: "expiry_date" },
      ]}
    />
  );
}
