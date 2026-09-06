import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppProvider } from './app/AppContext';
import { AppShell } from './app/AppShell';
import { CitizenLayout } from './citizen/CitizenLayout';
import { CitizenHelpPage } from './citizen/CitizenHelp';
import { CitizenHomePage } from './citizen/CitizenHome';
import { CitizenReportDetailPage } from './citizen/CitizenReportDetail';
import { CitizenReportPage } from './citizen/CitizenReport';
import { CitizenReportsPage } from './citizen/CitizenReports';
import { CitizenResultPage } from './citizen/CitizenResult';
import { CitizenScanPage } from './citizen/CitizenScan';
import { AuditPage } from './pages/Audit';
import { AnalyticsPage } from './pages/Analytics';
import { BatchesPage } from './pages/Batches';
import { ComplaintsPage } from './pages/Complaints';
import { ComplaintDetailPage } from './pages/ComplaintDetail';
import { DashboardPage } from './pages/Dashboard';
import { DepartmentPage } from './pages/Department';
import { EvidencePage } from './pages/Evidence';
import { HistoryPage } from './pages/History';
import { InspectionsPage } from './pages/Inspections';
import { InspectorPage } from './pages/Inspector';
import { NewInspectionPage } from './pages/NewInspection';
import { NotFoundPage } from './pages/NotFound';
import { ProductDetailPage } from './pages/ProductDetail';
import { ProductsPage } from './pages/Products';
import { RegulationsPage } from './pages/Regulations';
import { ReportsPage } from './pages/Reports';
import { ReportDetailPage } from './pages/ReportDetail';
import { ReviewPage } from './pages/Review';
import { RiskPage } from './pages/Risk';
import { SettingsPage } from './pages/Settings';
import { WorkspacePage } from './pages/Workspace';

/**
 * Root of the METRASIGHT inspection platform. A single BrowserRouter wraps the
 * AppProvider (backend connectivity + demo inspector context); every primary
 * destination renders inside the AppShell layout via <Outlet />.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="inspections" element={<InspectionsPage />} />
            <Route path="inspections/new" element={<NewInspectionPage />} />
            <Route path="inspections/:id" element={<WorkspacePage />} />
            <Route path="complaints" element={<ComplaintsPage />} />
            <Route path="complaints/:id" element={<ComplaintDetailPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="evidence" element={<EvidencePage />} />
            <Route path="regulations" element={<RegulationsPage />} />
            <Route path="batches" element={<BatchesPage />} />
            <Route path="risk" element={<RiskPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="reports/:id" element={<ReportDetailPage />} />
            {/* UI-09 — search, history & operational intelligence (read-only). */}
            <Route path="history" element={<HistoryPage />} />
            <Route path="products" element={<ProductsPage />} />
            <Route path="products/:id" element={<ProductDetailPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="settings" element={<SettingsPage />} />
            {/* Citizen Mode — its own shell: no sidebar/topbar, anonymous. */}
            <Route path="citizen" element={<CitizenLayout />}>
              <Route index element={<CitizenHomePage />} />
              <Route path="scan" element={<CitizenScanPage />} />
              <Route path="result" element={<CitizenResultPage />} />
              <Route path="report" element={<CitizenReportPage />} />
              <Route path="reports" element={<CitizenReportsPage />} />
              <Route path="reports/:id" element={<CitizenReportDetailPage />} />
              <Route path="help" element={<CitizenHelpPage />} />
            </Route>
            <Route path="department" element={<DepartmentPage />} />
            <Route path="inspector" element={<InspectorPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}
