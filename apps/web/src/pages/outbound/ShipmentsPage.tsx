import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function ShipmentsPage() {
  return (
    <DocumentListPage
      path="shipments"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("shipment")}
      columns={[
        {
          title: "Sales order",
          render: (_, r) =>
            r.ref_document && <Link className="wms-mono" to={`/sales-orders/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Customer", render: (_, r) => r.partner?.name },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
