import { AlertOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { Link } from "react-router";

import { useCan } from "@/api/me";
import { DocumentListPage, formatDateTime } from "@/components/documents";

export default function RecallsPage() {
  const can = useCan();
  return (
    <DocumentListPage
      path="recalls"
      statuses={["ACTIVE", "RELEASED"]}
      toolbarExtra={
        can("recall.create") && (
          <Link to="/trace">
            <Button danger icon={<AlertOutlined />}>Recall a batch</Button>
          </Link>
        )
      }
      columns={[
        { title: "Reason", dataIndex: "remark", ellipsis: true },
        { title: "Quarantine", dataIndex: ["location", "code"], render: (v?: string) => (v ? <span className="wms-mono">{v}</span> : <span className="wms-empty-value">—</span>) },
        { title: "Released", dataIndex: "posted_at", render: formatDateTime },
      ]}
    />
  );
}
