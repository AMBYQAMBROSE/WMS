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
}
