export interface UomBrief {
  id: string;
  code: string;
  name: string;
}

export interface PartnerBrief {
  id: string;
  code: string;
  name: string;
}

export interface ItemBrief {
  id: string;
  sku_code: string;
  name: string;
  is_batch_managed: boolean;
  is_expiry_managed: boolean;
  base_uom: UomBrief;
}

export interface LocationBrief {
  id: string;
  code: string;
  name: string;
  location_type: string;
}

export interface DocumentBrief {
  id: string;
  doc_type: string;
  doc_no: string;
  status: string;
}

export interface DocumentLine {
  id: string;
  line_no: number;
  item: ItemBrief;
  uom: UomBrief;
  qty_planned: number;
  qty_actual: number;
  batch_no: string | null;
  expiry_date: string | null;
  from_location: LocationBrief | null;
  to_location: LocationBrief | null;
  ref_line_id: string | null;
}

export interface DocumentSummary {
  id: string;
  doc_type: string;
  doc_no: string;
  status: string;
  partner: PartnerBrief | null;
  ref_document: DocumentBrief | null;
  location: LocationBrief | null;
  expected_date: string | null;
  posted_at: string | null;
  remark: string | null;
  created_at: string;
}

export interface Document extends DocumentSummary {
  lines: DocumentLine[];
}

export interface BusinessPartner {
  id: string;
  code: string;
  name: string;
  partner_type: "customer" | "supplier" | "both";
  contact_name: string | null;
  contact_phone: string | null;
  address: string | null;
  is_active: boolean;
}

export interface Item {
  id: string;
  sku_code: string;
  name: string;
  barcode: string | null;
  category: string | null;
  base_uom_id: string;
  is_batch_managed: boolean;
  is_expiry_managed: boolean;
  is_serial_managed: boolean;
  shelf_life_days: number | null;
  is_active: boolean;
}

export interface Location {
  id: string;
  code: string;
  name: string;
  location_type: string;
  parent_id: string | null;
  path: string;
  is_pickable: boolean;
  is_locked: boolean;
  capacity_qty: number | null;
  is_active: boolean;
}

export interface StockBalance {
  id: string;
  item: ItemBrief;
  location: LocationBrief;
  batch_no: string | null;
  expiry_date: string | null;
  qty_on_hand: number;
}

export interface StockLedgerEntry {
  id: string;
  item: ItemBrief;
  location: LocationBrief;
  batch_no: string | null;
  expiry_date: string | null;
  qty_change: number;
  movement_type: string;
  ref_line: { id: string; document: DocumentBrief } | null;
  occurred_at: string;
}
