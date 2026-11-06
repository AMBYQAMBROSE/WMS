import { WorkflowSteps, type WorkflowStep } from "@/components/ui";

/**
 * Lifecycle steppers for the multi-stage documents. They only read the document's existing status (and quantities
 * already on the page); nothing here changes what the backend allows.
 */

const PO_STEPS: WorkflowStep[] = [
  { key: "draft", label: "Draft" },
  { key: "confirmed", label: "Confirmed" },
  { key: "receiving", label: "Receiving" },
  { key: "received", label: "Received" },
];

const PO_INDEX: Record<string, number> = { DRAFT: 0, CONFIRMED: 1, PARTIALLY_RECEIVED: 2, RECEIVED: 3 };

export function PurchaseOrderSteps({ status }: { status: string }) {
  // A cancelled order shows no stepper: the status pill says it, and where it was cancelled is not known here
  if (status === "CANCELLED") return null;
  // Closing is only possible while partially received
  if (status === "CLOSED") return <WorkflowSteps steps={PO_STEPS} current={2} stopped={{ label: "Closed short" }} />;
  return <WorkflowSteps steps={PO_STEPS} current={PO_INDEX[status] ?? 0} />;
}

const SO_STEPS: WorkflowStep[] = [
  { key: "draft", label: "Draft" },
  { key: "confirmed", label: "Confirmed" },
  { key: "picking", label: "Allocated & picking" },
  { key: "shipping", label: "Shipping" },
  { key: "shipped", label: "Shipped" },
];

const SO_INDEX: Record<string, number> = { DRAFT: 0, CONFIRMED: 1, IN_PROGRESS: 2, PARTIALLY_SHIPPED: 3, SHIPPED: 4 };

export function SalesOrderSteps({ status, shippedAny }: { status: string; shippedAny: boolean }) {
  if (status === "CANCELLED") return null;
  // An order is closed while in progress or partially shipped: whether anything shipped tells which
  if (status === "CLOSED") return <WorkflowSteps steps={SO_STEPS} current={shippedAny ? 3 : 2} stopped={{ label: "Closed" }} />;
  return <WorkflowSteps steps={SO_STEPS} current={SO_INDEX[status] ?? 0} />;
}
