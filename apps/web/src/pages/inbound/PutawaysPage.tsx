import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function PutawaysPage() {
  return (
    <DocumentListPage
      path="putaways"
      createLabel="New putaway"
      createPerm="putaway.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        {
          title: "Source goods receipt",
          render: (_, r) => r.ref_document && <Link to={`/grns/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
