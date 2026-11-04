import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function GrnsPage() {
  return (
    <DocumentListPage
      path="grns"
      createLabel="New goods receipt"
      createPerm="grn.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("grn")}
      columns={[
        {
          title: "Purchase order",
          render: (_, r) =>
            r.ref_document && <Link to={`/purchase-orders/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Supplier", render: (_, r) => r.partner?.name },
        { title: "Receiving location", render: (_, r) => r.location?.code },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
