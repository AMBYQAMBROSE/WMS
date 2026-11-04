import { DocumentListPage } from "@/components/documents";

export default function PurchaseOrdersPage() {
  return (
    <DocumentListPage
      path="purchase-orders"
      createLabel="New purchase order"
      createPerm="purchase_order.create"
      statuses={["DRAFT", "CONFIRMED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"]}
      columns={[
        { title: "Supplier", render: (_, r) => r.partner?.name },
        { title: "Expected arrival", dataIndex: "expected_date" },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
