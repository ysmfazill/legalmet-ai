import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppProvider } from './app/AppContext';
import { AppShell } from './app/AppShell';
import { AuditPage } from './pages/Audit';
import { BatchesPage } from './pages/Batches';
import { DashboardPage } from './pages/Dashboard';
import { EvidencePage } from './pages/Evidence';
import { InspectionsPage } from './pages/Inspections';
import { NewInspectionPage } from './pages/NewInspection';
import { NotFoundPage } from './pages/NotFound';
import { RegulationsPage } from './pages/Regulations';
import { ReportsPage } from './pages/Reports';
import { ReviewPage } from './pages/Review';
import { RiskPage } from './pages/Risk';
import { SettingsPage } from './pages/Settings';
import { WorkspacePage } from './pages/Workspace';

/**
 * Root of the LegalMet AI inspection platform. A single BrowserRouter wraps the
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
            <Route path="review" element={<ReviewPage />} />
            <Route path="evidence" element={<EvidencePage />} />
            <Route path="regulations" element={<RegulationsPage />} />
            <Route path="batches" element={<BatchesPage />} />
            <Route path="risk" element={<RiskPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}
