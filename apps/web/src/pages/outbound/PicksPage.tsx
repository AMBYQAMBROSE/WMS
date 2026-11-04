import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function PicksPage() {
  return (
    <DocumentListPage
      path="picks"
      statuses={["OPEN", "POSTED", "CANCELLED"]}
      batchActions={[{ key: "cancel", label: "Cancel", perm: "pick.cancel", statuses: ["OPEN"], danger: true }]}
      columns={[
        {
          title: "Sales order",
          render: (_, r) =>
            r.ref_document && <Link to={`/sales-orders/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Customer", render: (_, r) => r.partner?.name },
        { title: "Staging", render: (_, r) => r.location?.code },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
