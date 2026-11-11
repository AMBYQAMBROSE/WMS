export const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  DRAFT: { text: "Draft", color: "default" },
  CONFIRMED: { text: "Confirmed", color: "blue" },
  PARTIALLY_RECEIVED: { text: "Partially received", color: "orange" },
  RECEIVED: { text: "Received", color: "green" },
  CLOSED: { text: "Closed", color: "purple" },
  CANCELLED: { text: "Cancelled", color: "red" },
  POSTED: { text: "Posted", color: "green" },
  COUNTING: { text: "Counting", color: "orange" },
  IN_PROGRESS: { text: "In progress", color: "processing" },
  PARTIALLY_SHIPPED: { text: "Partially shipped", color: "orange" },
  SHIPPED: { text: "Shipped", color: "green" },
  OPEN: { text: "To pick", color: "blue" },
};

export const PARTNER_TYPE_LABELS: Record<string, string> = {
  customer: "Customer",
  supplier: "Supplier",
  both: "Customer/Supplier",
};

export const LOCATION_TYPE_LABELS: Record<string, string> = {
  WAREHOUSE: "Warehouse",
  ZONE: "Zone",
  AISLE: "Aisle",
  RACK: "Rack",
  BIN: "Bin",
  DOCK: "Dock",
};

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  RECEIVE: "Receipt",
  PUTAWAY_OUT: "Putaway out",
  PUTAWAY_IN: "Putaway in",
  MOVE_OUT: "Move out",
  MOVE_IN: "Move in",
  ADJUST_IN: "Adjustment +",
  ADJUST_OUT: "Adjustment -",
  COUNT_GAIN: "Count gain",
  COUNT_LOSS: "Count loss",
  PICK_OUT: "Pick out",
  PICK_IN: "Pick to staging",
  SHIP_OUT: "Shipment",
  RETURN_IN: "Customer return",
  RETURN_OUT: "Return to supplier",
  REPACK_OUT: "Repack consumed",
  REPACK_IN: "Repack produced",
};

export const PERMISSION_MODULE_LABELS: Record<string, string> = {
  inbound: "Inbound",
  inventory: "Inventory",
  outbound: "Outbound",
  returns: "Returns & returnable assets",
  master_data: "Master data",
  mobile: "PDA",
  system: "System",
  report: "Dashboard & reports",
  integration: "Integrations",
};

/** Document type -> display name */
export const DOC_TYPE_LABELS: Record<string, string> = {
  PO: "Purchase order", GRN: "Goods receipt", PUTAWAY: "Putaway", MOVE: "Move", ADJUST: "Stock adjustment", COUNT: "Cycle count",
  SO: "Sales order", PICK: "Pick list", SHIP: "Shipment", RETURN_IN: "Customer return", RETURN_OUT: "Return to supplier", REPACK: "Repack",
};

/** Document type in the stock ledger -> frontend route, for linking document numbers to their detail page */
export const DOC_PATHS: Record<string, string> = {
  PO: "purchase-orders",
  GRN: "grns",
  PUTAWAY: "putaways",
  MOVE: "moves",
  ADJUST: "adjustments",
  COUNT: "cycle-counts",
  SO: "sales-orders",
  PICK: "picks",
  SHIP: "shipments",
  RETURN_IN: "returns-in",
  RETURN_OUT: "returns-out",
  REPACK: "repacks",
};

/** Audit log entity types (app/models/audit.py) */
export const AUDIT_ENTITY_LABELS: Record<string, string> = {
  tenant: "Company",
  feature_flag: "Feature flag",
  user: "User",
  role: "Role",
  business_partner: "Business partner",
  item: "Item",
  item_barcode: "Item barcode",
  item_uom_conversion: "Unit conversion",
  uom: "Unit of measure",
  location: "Location",
  label_profile: "Label layout",
  reason_code: "Reason code",
  returnable_asset_type: "Returnable asset type",
  returnable_asset_txn: "Returnable asset movement",
  doc_number_rule: "Document numbering",
  integration_connector: "Integration connector",
  document: "Document",
  document_line: "Document line",
  shipment_info: "Loading details",
  count_entry: "Count entry",
};

export const AUDIT_ACTION_LABELS: Record<string, { text: string; color: string }> = {
  CREATE: { text: "Created", color: "green" },
  UPDATE: { text: "Changed", color: "blue" },
  DELETE: { text: "Deleted", color: "red" },
  PRINT: { text: "Printed", color: "default" },
};
