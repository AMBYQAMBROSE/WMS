import { lazy, Suspense } from "react";

import { Spin } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import MainLayout from "@/layouts/MainLayout";
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

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Spin style={{ margin: 48 }} />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route index element={<Navigate to="/purchase-orders" replace />} />
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
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
