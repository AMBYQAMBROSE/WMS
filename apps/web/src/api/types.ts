/**
 * API response types, generated from the backend OpenAPI schema (see schema.d.ts and npm run gen:api).
 * The names here are the ones the app uses; never hand-write a response shape, alias the generated one.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type UomBrief = Schemas["UomBrief"];
export type PartnerBrief = Schemas["PartnerBrief"];
export type ItemBrief = Schemas["ItemBrief"];
export type LocationBrief = Schemas["LocationBrief"];
export type DocumentBrief = Schemas["DocumentBrief"];
export type DocumentLine = Schemas["DocumentLineRead"];
export type ReasonBrief = Schemas["ReasonBrief"];
export type ReasonCode = Schemas["ReasonCodeRead"];
export type DocumentSummary = Schemas["DocumentSummary"];
export type Document = Schemas["DocumentRead"];
export type CountEntry = Schemas["CountEntryRead"];
export type CountLine = Schemas["CountLineRead"];
export type CycleCount = Schemas["CountRead"];
export type SalesOrderLine = Schemas["SalesOrderLineRead"];
export type SalesOrder = Schemas["SalesOrderRead"];
export type PickLine = Schemas["PickLineRead"];
export type Pick = Schemas["PickRead"];
export type Shortage = Schemas["ShortageRead"];
export type ShipmentInfo = Schemas["ShipmentInfoRead"];
export type Shipment = Schemas["ShipmentRead"];
export type ShortageRow = Schemas["ShortageReportRow"];
export type BusinessPartner = Schemas["BusinessPartnerRead"];
export type Item = Schemas["ItemRead"];
export type Location = Schemas["LocationRead"];
export type StockBalance = Schemas["StockBalanceRead"];
export type StockLedgerEntry = Schemas["StockLedgerRead"];
export type AssetType = Schemas["AssetTypeRead"];
export type AssetTxn = Schemas["AssetTxnRead"];
export type AssetBalance = Schemas["AssetBalanceRow"];
export type DailyFlow = Schemas["DailyFlow"];
export type Dashboard = Schemas["Dashboard"];
export type TurnoverRow = Schemas["TurnoverRow"];
export type PickerKpiRow = Schemas["PickerKpiRow"];
export type ExpiryRow = Schemas["ExpiryRow"];
export type PartnerLedgerRow = Schemas["PartnerLedgerRow"];
export type Connector = Schemas["ConnectorRead"];
export type ConnectorWithSecret = Schemas["ConnectorWithSecret"];
export type EventType = Schemas["EventTypeRead"];
export type IntegrationJob = Schemas["JobRead"];
export type IntegrationLog = Schemas["IntegrationLogRead"];
export type IntegrationJobDetail = Schemas["JobDetail"];
export type IntegrationSummary = Schemas["IntegrationSummary"];
