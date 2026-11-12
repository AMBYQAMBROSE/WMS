export interface MobileItem {
  id: string;
  sku_code: string;
  name: string;
  barcode: string | null;
  base_uom_id: string;
  is_batch_managed: boolean;
  is_expiry_managed: boolean;
}

export interface MobileBarcode {
  barcode: string;
  item_id: string;
  uom_id: string;
}

export interface MobileUom {
  id: string;
  code: string;
  name: string;
}

export interface MobileConversion {
  item_id: string;
  from_uom_id: string;
  to_uom_id: string;
  factor: number;
}

export interface MobileLocation {
  id: string;
  code: string;
  name: string;
  location_type: string;
  is_locked: boolean;
}

export interface MasterData {
  generated_at: string;
  items: MobileItem[];
  barcodes: MobileBarcode[];
  uoms: MobileUom[];
  conversions: MobileConversion[];
  locations: MobileLocation[];
}

export interface ItemBrief {
  id: string;
  sku_code: string;
  name: string;
  is_batch_managed: boolean;
  is_expiry_managed: boolean;
  base_uom: { id: string; code: string; name: string };
}

export interface DocumentLine {
  id: string;
  line_no: number;
  item: ItemBrief;
  uom: { id: string; code: string; name: string };
  qty_planned: number;
  qty_actual: number;
  batch_no: string | null;
  expiry_date: string | null;
}

export interface Document {
  id: string;
  doc_type: string;
  doc_no: string;
  status: string;
  partner: { id: string; code: string; name: string } | null;
  lines: DocumentLine[];
}

export interface DocumentSummary {
  id: string;
  doc_no: string;
  status: string;
  remark: string | null;
  created_at: string;
}

export interface CountLine {
  id: string;
  item: ItemBrief;
  /** Book quantity; null without the view permission (blind count) */
  qty_planned: number | null;
  qty_actual: number;
  counted_at: string | null;
  batch_no: string | null;
  expiry_date: string | null;
  to_location: { id: string; code: string; name: string } | null;
}

export interface CycleCount extends DocumentSummary {
  count_locations: { location: { id: string; code: string; name: string } }[];
  lines: CountLine[];
}

export interface PickLine {
  id: string;
  line_no: number;
  item: ItemBrief;
  uom: { id: string; code: string; name: string };
  qty_planned: number;
  qty_actual: number;
  batch_no: string | null;
  expiry_date: string | null;
  from_location: { id: string; code: string; name: string } | null;
  confirmed_at: string | null;
}

export interface Pick extends DocumentSummary {
  partner: { id: string; code: string; name: string } | null;
  ref_document: { id: string; doc_no: string } | null;
  location: { id: string; code: string; name: string } | null;
  lines: PickLine[];
}

export interface StockBalance {
  id: string;
  item: ItemBrief;
  location: { id: string; code: string; name: string };
  batch_no: string | null;
  expiry_date: string | null;
  qty_on_hand: number;
  qty_allocated: number;
}

export interface PutawayLine {
  id: string;
  line_no: number;
  item: ItemBrief;
  uom: { id: string; code: string; name: string };
  /** Quantity of this line; a partial put splits the rest off as a new line */
  qty_planned: number;
  qty_actual: number;
  batch_no: string | null;
  expiry_date: string | null;
  /** Suggested bin while open (null: any bin); the bin used once put away */
  to_location: { id: string; code: string; name: string } | null;
  confirmed_at: string | null;
}

/** Putaway sheet made from a posted receipt (status TO_PUT_AWAY while being worked) */
export interface PutawaySheet extends DocumentSummary {
  ref_document: { id: string; doc_no: string } | null;
  location: { id: string; code: string; name: string } | null;
  lines: PutawayLine[];
}

export interface ShipmentInfo {
  carrier: string | null;
  vehicle_no: string | null;
  driver_name: string | null;
  driver_phone: string | null;
  seal_no: string | null;
}

export interface ShipmentLine {
  id: string;
  line_no: number;
  item: ItemBrief;
  uom: { id: string; code: string; name: string };
  /** Quantity to ship (base units) */
  qty_actual: number;
  /** Scanned onto the vehicle so far */
  qty_checked: number;
  batch_no: string | null;
  expiry_date: string | null;
  from_location: { id: string; code: string; name: string } | null;
}

/** Delivery order (shipment); posted only once every piece is scanned */
export interface Shipment extends DocumentSummary {
  partner: { id: string; code: string; name: string } | null;
  ref_document: { id: string; doc_no: string } | null;
  shipment_info: ShipmentInfo | null;
  lines: ShipmentLine[];
}

/** A document whose number was scanned (GET /mobile/lookup) */
export interface DocumentHit {
  id: string;
  doc_type: string;
  doc_no: string;
  status: string;
  ref_document_id: string | null;
}

export interface LoadingHistory {
  carriers: string[];
  vehicles: ShipmentInfo[];
}
