import { DocumentListPage } from "@/components/documents";

export default function SalesOrdersPage() {
  return (
    <DocumentListPage
      path="sales-orders"
      createLabel="New sales order"
      createPerm="sales_order.create"
      statuses={["DRAFT", "CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED", "SHIPPED", "CLOSED", "CANCELLED"]}
      columns={[
        { title: "Customer", render: (_, r) => r.partner?.name },
        { title: "Requested ship date", dataIndex: "expected_date" },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
