import { lazy, Suspense } from "react";

import { Spin } from "antd";
import { BrowserRouter, Route, Routes } from "react-router";

import MainLayout, { HomeRedirect } from "@/layouts/MainLayout";
import LoginPage from "@/pages/LoginPage";
import ProtectedRoute from "@/routes/ProtectedRoute";

const BusinessPartnersPage = lazy(() => import("@/pages/BusinessPartnersPage"));
const ItemsPage = lazy(() => import("@/pages/ItemsPage"));
const LocationsPage = lazy(() => import("@/pages/LocationsPage"));
const PurchaseOrdersPage = lazy(() => import("@/pages/inbound/PurchaseOrdersPage"));
const PurchaseOrderFormPage = lazy(() => import("@/pages/inbound/PurchaseOrderFormPage"));
const PurchaseOrderDetailPage = lazy(() => import("@/pages/inbound/PurchaseOrderDetailPage"));
const GrnsPage = lazy(() => import("@/pages/inbound/GrnsPage"));
const GrnCreatePage = lazy(() => import("@/pages/inbound/GrnCreatePage"));
const GrnDetailPage = lazy(() => import("@/pages/inbound/GrnDetailPage"));
const PutawaysPage = lazy(() => import("@/pages/inbound/PutawaysPage"));
const PutawayCreatePage = lazy(() => import("@/pages/inbound/PutawayCreatePage"));
const PutawayDetailPage = lazy(() => import("@/pages/inbound/PutawayDetailPage"));
const StockPage = lazy(() => import("@/pages/inventory/StockPage"));
const AdjustmentsPage = lazy(() => import("@/pages/inventory/AdjustmentsPage"));
const AdjustmentCreatePage = lazy(() => import("@/pages/inventory/AdjustmentCreatePage"));
const AdjustmentDetailPage = lazy(() => import("@/pages/inventory/AdjustmentDetailPage"));
const MovesPage = lazy(() => import("@/pages/inventory/MovesPage"));
const MoveCreatePage = lazy(() => import("@/pages/inventory/MoveCreatePage"));
const MoveDetailPage = lazy(() => import("@/pages/inventory/MoveDetailPage"));
const CycleCountsPage = lazy(() => import("@/pages/inventory/CycleCountsPage"));
const CycleCountCreatePage = lazy(() => import("@/pages/inventory/CycleCountCreatePage"));
const CycleCountDetailPage = lazy(() => import("@/pages/inventory/CycleCountDetailPage"));
const ReasonCodesPage = lazy(() => import("@/pages/ReasonCodesPage"));
const SalesOrdersPage = lazy(() => import("@/pages/outbound/SalesOrdersPage"));
const SalesOrderFormPage = lazy(() => import("@/pages/outbound/SalesOrderFormPage"));
const SalesOrderDetailPage = lazy(() => import("@/pages/outbound/SalesOrderDetailPage"));
const PicksPage = lazy(() => import("@/pages/outbound/PicksPage"));
const PickDetailPage = lazy(() => import("@/pages/outbound/PickDetailPage"));
const ShipmentsPage = lazy(() => import("@/pages/outbound/ShipmentsPage"));
const ShipmentDetailPage = lazy(() => import("@/pages/outbound/ShipmentDetailPage"));
const ShortagesPage = lazy(() => import("@/pages/outbound/ShortagesPage"));
const UsersPage = lazy(() => import("@/pages/system/UsersPage"));
const RolesPage = lazy(() => import("@/pages/system/RolesPage"));
const FeaturesPage = lazy(() => import("@/pages/system/FeaturesPage"));
const IntegrationPage = lazy(() => import("@/pages/system/IntegrationPage"));
const ImportPage = lazy(() => import("@/pages/system/ImportPage"));
const AuditLogPage = lazy(() => import("@/pages/system/AuditLogPage"));
const SystemHealthPage = lazy(() => import("@/pages/system/SystemHealthPage"));
const DashboardPage = lazy(() => import("@/pages/reports/DashboardPage"));
const AssistantPage = lazy(() => import("@/pages/reports/AssistantPage"));
const TurnoverReportPage = lazy(() => import("@/pages/reports/TurnoverReportPage"));
const PickerKpiPage = lazy(() => import("@/pages/reports/PickerKpiPage"));
const ExpiryReportPage = lazy(() => import("@/pages/reports/ExpiryReportPage"));
const PartnerLedgerPage = lazy(() => import("@/pages/reports/PartnerLedgerPage"));
const RepacksPage = lazy(() => import("@/pages/inventory/RepacksPage"));
const RepackCreatePage = lazy(() => import("@/pages/inventory/RepackCreatePage"));
const RepackDetailPage = lazy(() => import("@/pages/inventory/RepackDetailPage"));
const ReturnsInPage = lazy(() => import("@/pages/returns/ReturnsInPage"));
const ReturnInCreatePage = lazy(() => import("@/pages/returns/ReturnInCreatePage"));
const ReturnInDetailPage = lazy(() => import("@/pages/returns/ReturnInDetailPage"));
const ReturnsOutPage = lazy(() => import("@/pages/returns/ReturnsOutPage"));
const ReturnOutCreatePage = lazy(() => import("@/pages/returns/ReturnOutCreatePage"));
const ReturnOutDetailPage = lazy(() => import("@/pages/returns/ReturnOutDetailPage"));
const ReturnableAssetsPage = lazy(() => import("@/pages/returns/ReturnableAssetsPage"));

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Spin style={{ margin: 48 }} />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route index element={<HomeRedirect />} />
              <Route path="business-partners" element={<BusinessPartnersPage />} />
              <Route path="items" element={<ItemsPage />} />
              <Route path="locations" element={<LocationsPage />} />
              <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
              <Route path="purchase-orders/new" element={<PurchaseOrderFormPage />} />
              <Route path="purchase-orders/:id" element={<PurchaseOrderDetailPage />} />
              <Route path="purchase-orders/:id/edit" element={<PurchaseOrderFormPage />} />
              <Route path="grns" element={<GrnsPage />} />
              <Route path="grns/new" element={<GrnCreatePage />} />
              <Route path="grns/:id" element={<GrnDetailPage />} />
              <Route path="putaways" element={<PutawaysPage />} />
              <Route path="putaways/new" element={<PutawayCreatePage />} />
              <Route path="putaways/:id" element={<PutawayDetailPage />} />
              <Route path="stock" element={<StockPage />} />
              <Route path="adjustments" element={<AdjustmentsPage />} />
              <Route path="adjustments/new" element={<AdjustmentCreatePage />} />
              <Route path="adjustments/:id" element={<AdjustmentDetailPage />} />
              <Route path="moves" element={<MovesPage />} />
              <Route path="moves/new" element={<MoveCreatePage />} />
              <Route path="moves/:id" element={<MoveDetailPage />} />
              <Route path="cycle-counts" element={<CycleCountsPage />} />
              <Route path="cycle-counts/new" element={<CycleCountCreatePage />} />
              <Route path="cycle-counts/:id" element={<CycleCountDetailPage />} />
              <Route path="reason-codes" element={<ReasonCodesPage />} />
              <Route path="sales-orders" element={<SalesOrdersPage />} />
              <Route path="sales-orders/new" element={<SalesOrderFormPage />} />
              <Route path="sales-orders/:id" element={<SalesOrderDetailPage />} />
              <Route path="sales-orders/:id/edit" element={<SalesOrderFormPage />} />
              <Route path="picks" element={<PicksPage />} />
              <Route path="picks/:id" element={<PickDetailPage />} />
              <Route path="shipments" element={<ShipmentsPage />} />
              <Route path="shipments/:id" element={<ShipmentDetailPage />} />
              <Route path="shortages" element={<ShortagesPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="roles" element={<RolesPage />} />
              <Route path="features" element={<FeaturesPage />} />
              <Route path="integration" element={<IntegrationPage />} />
              <Route path="imports" element={<ImportPage />} />
              <Route path="audit-log" element={<AuditLogPage />} />
              <Route path="system-health" element={<SystemHealthPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="assistant" element={<AssistantPage />} />
              <Route path="reports/turnover" element={<TurnoverReportPage />} />
              <Route path="reports/picker-kpi" element={<PickerKpiPage />} />
              <Route path="reports/expiry" element={<ExpiryReportPage />} />
              <Route path="reports/partner-ledger" element={<PartnerLedgerPage />} />
              <Route path="repacks" element={<RepacksPage />} />
              <Route path="repacks/new" element={<RepackCreatePage />} />
              <Route path="repacks/:id" element={<RepackDetailPage />} />
              <Route path="returns-in" element={<ReturnsInPage />} />
              <Route path="returns-in/new" element={<ReturnInCreatePage />} />
              <Route path="returns-in/:id" element={<ReturnInDetailPage />} />
              <Route path="returns-out" element={<ReturnsOutPage />} />
              <Route path="returns-out/new" element={<ReturnOutCreatePage />} />
              <Route path="returns-out/:id" element={<ReturnOutDetailPage />} />
              <Route path="returnable-assets" element={<ReturnableAssetsPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
