import { BrowserRouter, Route, Routes } from "react-router-dom";

import MainLayout from "@/layouts/MainLayout";
import BusinessPartnersPage from "@/pages/BusinessPartnersPage";
import ItemsPage from "@/pages/ItemsPage";
import LocationsPage from "@/pages/LocationsPage";
import LoginPage from "@/pages/LoginPage";
import ProtectedRoute from "@/routes/ProtectedRoute";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<MainLayout />}>
            <Route index element={<BusinessPartnersPage />} />
            <Route path="business-partners" element={<BusinessPartnersPage />} />
            <Route path="items" element={<ItemsPage />} />
            <Route path="locations" element={<LocationsPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
