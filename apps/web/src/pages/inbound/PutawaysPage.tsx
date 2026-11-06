import { Link } from "react-router";

import { DocumentListPage, formatDateTime } from "@/components/documents";
import { postAndCancel } from "@/components/ListTools";

export default function PutawaysPage() {
  return (
    <DocumentListPage
      path="putaways"
      createLabel="New putaway"
      createPerm="putaway.create"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      batchActions={postAndCancel("putaway")}
      columns={[
        {
          title: "Source goods receipt",
          render: (_, r) => r.ref_document && <Link className="wms-mono" to={`/grns/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "Posted", dataIndex: "posted_at", render: formatDateTime },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
