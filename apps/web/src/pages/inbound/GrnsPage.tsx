import { Link } from "react-router-dom";

import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function GrnsPage() {
  return (
    <DocumentListPage
      path="grns"
      createLabel="新建收货单"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        {
          title: "采购单",
          render: (_, r) =>
            r.ref_document && <Link to={`/purchase-orders/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "供应商", render: (_, r) => r.partner?.name },
        { title: "收货仓位", render: (_, r) => r.location?.code },
        { title: "过账时间", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
