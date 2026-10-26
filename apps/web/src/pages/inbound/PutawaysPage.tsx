import { Link } from "react-router-dom";

import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function PutawaysPage() {
  return (
    <DocumentListPage
      path="putaways"
      createLabel="新建上架单"
      statuses={["DRAFT", "POSTED", "CANCELLED"]}
      columns={[
        {
          title: "来源收货单",
          render: (_, r) => r.ref_document && <Link to={`/grns/${r.ref_document.id}`}>{r.ref_document.doc_no}</Link>,
        },
        { title: "过账时间", dataIndex: "posted_at", render: formatDateTime },
        { title: "备注", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
