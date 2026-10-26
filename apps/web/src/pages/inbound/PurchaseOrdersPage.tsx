import { DocumentListPage } from "@/components/documents";

export default function PurchaseOrdersPage() {
  return (
    <DocumentListPage
      path="purchase-orders"
      createLabel="新建采购单"
      statuses={["DRAFT", "CONFIRMED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"]}
      columns={[
        { title: "供应商", render: (_, r) => r.partner?.name },
        { title: "预计到货", dataIndex: "expected_date" },
        { title: "备注", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
