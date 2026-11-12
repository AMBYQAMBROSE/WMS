import { ImportButton } from "@/components/ImportRunner";
import { DocumentListPage } from "@/components/documents";

export default function PurchaseOrdersPage() {
  return (
    <DocumentListPage
      path="purchase-orders"
      createLabel="New purchase order"
      createPerm="purchase_order.create"
      toolbarExtra={<ImportButton kind={{ key: "purchase_orders", name: "Purchase orders" }} perm="purchase_order.create" />}
      statuses={["DRAFT", "CONFIRMED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"]}
      batchActions={[
        { key: "confirm", label: "Confirm", perm: "purchase_order.confirm", statuses: ["DRAFT"] },
        { key: "close", label: "Close", perm: "purchase_order.close", statuses: ["PARTIALLY_RECEIVED"] },
        { key: "cancel", label: "Cancel", perm: "purchase_order.cancel", statuses: ["DRAFT", "CONFIRMED"], danger: true },
      ]}
      columns={[
        { title: "Supplier", render: (_, r) => r.partner?.name },
        { title: "Expected arrival", dataIndex: "expected_date" },
        { title: "Remark", dataIndex: "remark", ellipsis: true },
      ]}
    />
  );
}
