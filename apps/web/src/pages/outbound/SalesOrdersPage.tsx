import { DocumentListPage } from "@/components/documents";

export default function SalesOrdersPage() {
  return (
    <DocumentListPage
      path="sales-orders"
      createLabel="New sales order"
      createPerm="sales_order.create"
      statuses={["DRAFT", "CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED", "SHIPPED", "CLOSED", "CANCELLED"]}
      batchActions={[
        { key: "confirm", label: "Confirm", perm: "sales_order.confirm", statuses: ["DRAFT"] },
        { key: "close", label: "Close", perm: "sales_order.close", statuses: ["CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED"] },
        { key: "cancel", label: "Cancel", perm: "sales_order.cancel", statuses: ["DRAFT", "CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED"], danger: true },
      ]}
      columns={[
        { title: "Customer", render: (_, r) => r.partner?.name },
        { title: "Requested ship date", dataIndex: "expected_date" },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
