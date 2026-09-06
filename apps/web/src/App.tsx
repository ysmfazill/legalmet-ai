import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppErrorBoundary } from './components/AppErrorBoundary';
import { AppProvider } from './app/AppContext';
import { AppShell } from './app/AppShell';
import { EntryPage } from './app/EntryPage';
import { LoginPage } from './app/LoginPage';
import { RequireAuth } from './app/RequireAuth';
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
 * Root of the METRASIGHT platform.
 *
 * Routing contract (entry-flow):
 *   `/`                 PUBLIC entry page — choose Citizen / Inspector / Department.
 *   `/login/*`          PUBLIC staff login pages (real POST /auth/login).
 *   `/citizen/*`        PUBLIC Citizen Mode — anonymous, no account, own shell.
 *   `/dashboard`, …     STAFF workspace — every route behind RequireAuth; an
 *                       anonymous visitor is redirected to the entry page.
 *                       Real authorization is the backend's per-endpoint
 *                       JWT + role checks; the guard is UX, not security.
 */
export default function App() {
  return (
    <AppErrorBoundary>
      <BrowserRouter>
        <AppProvider>
        <Routes>
            {/* PUBLIC — entry + staff login */}
            <Route index element={<EntryPage />} />
            <Route path="login/inspector" element={<LoginPage mode="inspector" />} />
            <Route path="login/department" element={<LoginPage mode="department" />} />

            {/* PUBLIC — Citizen Mode (same shell placement as before the split) */}
            <Route element={<AppShell />}>
              <Route path="citizen" element={<CitizenLayout />}>
                <Route index element={<CitizenHomePage />} />
                <Route path="scan" element={<CitizenScanPage />} />
                <Route path="result" element={<CitizenResultPage />} />
                <Route path="report" element={<CitizenReportPage />} />
                <Route path="reports" element={<CitizenReportsPage />} />
                <Route path="reports/:id" element={<CitizenReportDetailPage />} />
                <Route path="help" element={<CitizenHelpPage />} />
              </Route>
            </Route>

            {/* STAFF — authenticated workspace */}
            <Route
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route path="dashboard" element={<DashboardPage />} />
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
              <Route path="department" element={<DepartmentPage />} />
              <Route path="inspector" element={<InspectorPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
        </Routes>
        </AppProvider>
      </BrowserRouter>
    </AppErrorBoundary>
  );
}
