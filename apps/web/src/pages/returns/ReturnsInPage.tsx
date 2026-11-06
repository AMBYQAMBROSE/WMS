import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function ReturnsInPage() {
  return (
    <DocumentListPage
      path="returns-in"
      createLabel="New customer return"
      createPerm="return_in.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("return_in")}
      columns={[
        { title: "Customer", render: (_, r) => r.partner?.name },
        {
          title: "Original order",
          render: (_, r) => r.ref_document && <Link className="wms-mono" to={`/sales-orders/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Reason", render: (_, r) => r.reason_code?.name },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
