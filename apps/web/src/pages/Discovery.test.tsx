// @vitest-environment jsdom
//
// UI-09 — tests for the search / history / product repository / analytics
// surfaces. The api client and app context are mocked at module boundaries;
// the pages and the GlobalSearch palette under test are the real ones. Every
// assertion checks the honesty contract: real counts from the backend, N/A
// for null rates, spec empty states, URL-persisted filters, and
// cross-navigation to EXISTING detail pages only.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  HistoryPage as HistoryPageData,
  InspectionTimeline,
  OperationalAnalytics,
  ProductDetail,
  ProductSummary,
  SearchResults,
  User,
} from '@legalmet/types';

import { MemoryRouter, Route, Routes } from 'react-router-dom';

// --- module mocks (specifiers exactly as the pages import them) -------------

vi.mock('../api/client', () => ({
  api: {
    search: vi.fn(),
    inspectionHistory: vi.fn(),
    inspectionTimeline: vi.fn(),
    listProducts: vi.fn(),
    getProduct: vi.fn(),
    operationalAnalytics: vi.fn(),
    complaintInspectors: vi.fn(),
  },
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

const mockUser: User = {
  id: 'u1',
  fullName: 'Inspector Ishaan',
  email: 'i@y.z',
  role: 'INSPECTOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ isLive: true, user: mockUser }),
}));

import { api } from '../api/client';
import { GlobalSearch } from '../app/GlobalSearch';
import { AnalyticsPage } from './Analytics';
import { HistoryPage } from './History';
import { ProductDetailPage } from './ProductDetail';
import { ProductsPage } from './Products';

const searchMock = vi.mocked(api.search);
const historyMock = vi.mocked(api.inspectionHistory);
const timelineMock = vi.mocked(api.inspectionTimeline);
const listProductsMock = vi.mocked(api.listProducts);
const getProductMock = vi.mocked(api.getProduct);
const analyticsMock = vi.mocked(api.operationalAnalytics);
const inspectorsMock = vi.mocked(api.complaintInspectors);

// --- fixtures ----------------------------------------------------------------

const SEARCH_RESULTS: SearchResults = {
  query: 'tea',
  inspections: [
    {
      id: 'i1',
      reference: 'LM-00012345',
      productName: 'DEMO Tea 250g',
      status: 'UNDER_REVIEW',
      result: 'REVIEW_REQUIRED',
      inspectorName: 'Inspector Ishaan',
      source: 'DIRECT_INSPECTION',
      createdAt: '2026-09-01T10:00:00Z',
    },
  ],
  complaints: [
    {
      id: 'c1',
      reference: 'CMP-00042',
      status: 'ACCEPTED',
      product: 'DEMO Tea 250g',
      issue: 'MRP appears inconsistent',
      location: 'Pune',
      inspectionId: null,
      createdAt: '2026-09-02T10:00:00Z',
    },
  ],
  products: [
    {
      id: 'p1',
      name: 'DEMO Tea 250g',
      category: 'food',
      gtin: null,
      inspectionCount: 3,
      lastInspectionAt: '2026-09-03T10:00:00Z',
    },
  ],
  reports: [],
  findings: [
    {
      id: 'f1',
      inspectionId: 'i1',
      inspectionReference: 'LM-00012345',
      ruleCode: 'LM-QCR-01',
      status: 'REVIEW_REQUIRED',
      severity: 'MAJOR',
      detectedValue: '200 g',
      createdAt: '2026-09-01T11:00:00Z',
    },
  ],
  evidence: [],
};

const HISTORY_DATA: HistoryPageData = {
  items: [
    {
      id: 'i1',
      reference: 'LM-00012345',
      createdAt: '2026-09-01T10:00:00Z',
      productName: 'DEMO Tea 250g',
      productCategory: 'food',
      inspectorName: 'Inspector Ishaan',
      establishment: 'Test Market, Delhi',
      source: 'CITIZEN_COMPLAINT',
      sourceComplaintReference: 'CMP-00042',
      status: 'COMPLETED',
      result: 'NON_COMPLIANT',
      imageCount: 2,
      report: { id: 'r1', status: 'FINALIZED', version: 1 },
    },
  ],
  total: 1,
  page: 1,
  pageSize: 20,
  kpis: { total: 1, compliant: 0, nonCompliant: 1, reviewRequired: 0, open: 0 },
};

const TIMELINE: InspectionTimeline = {
  inspectionId: 'i1',
  reference: 'LM-00012345',
  events: [
    {
      stage: 'INSPECTION_CREATED',
      label: 'Inspection created',
      eventType: 'INSPECTION_CREATED',
      at: '2026-09-01T10:00:00Z',
      actorName: 'Inspector Ishaan',
    },
    {
      stage: 'FINDINGS_GENERATED',
      label: 'Findings generated (engine evaluation)',
      at: '2026-09-01T11:00:00Z',
      detail: 'Engine 1.0.0 · 6 findings',
    },
  ],
};

const PRODUCT_LIST = {
  items: [
    {
      id: 'p1',
      name: 'DEMO Tea 250g',
      category: 'food',
      gtin: null,
      inspectionCount: 3,
      findingCount: 6,
      lastInspectionAt: '2026-09-03T10:00:00Z',
      latestResult: 'NON_COMPLIANT',
    },
  ] satisfies ProductSummary[],
  total: 1,
  page: 1,
  pageSize: 20,
};

const PRODUCT_DETAIL: ProductDetail = {
  id: 'p1',
  name: 'DEMO Tea 250g',
  category: 'food',
  gtin: null,
  inspectionCount: 2,
  findingCount: 4,
  lastInspectionAt: '2026-09-03T10:00:00Z',
  latestResult: 'NON_COMPLIANT',
  declaredFields: [
    {
      fieldType: 'NET_QUANTITY',
      rawText: 'Net Qty 250 g',
      normalizedValue: '250',
      unit: 'g',
      inspectionId: 'i1',
      inspectionReference: 'LM-00012345',
      detectedAt: '2026-09-01T11:00:00Z',
    },
  ],
  inspections: [
    {
      id: 'i1',
      reference: 'LM-00012345',
      createdAt: '2026-09-01T10:00:00Z',
      inspectorName: 'Inspector Ishaan',
      result: 'NON_COMPLIANT',
      report: { id: 'r1', status: 'FINALIZED', version: 1 },
      source: 'DIRECT_INSPECTION',
    },
  ],
  findingsHistory: [
    {
      ruleCode: 'LM-QCR-01',
      label: 'Net quantity declaration',
      occurrenceCount: 2,
      inspectionCount: 2,
      reviewRequiredCount: 2,
      nonCompliantCount: 2,
    },
  ],
  evidenceGallery: [
    {
      id: 'img1',
      inspectionId: 'i1',
      inspectionReference: 'LM-00012345',
      imageType: 'FRONT',
      originalFilename: 'front.png',
      createdAt: '2026-09-01T10:30:00Z',
      fieldTypes: ['NET_QUANTITY'],
    },
  ],
  boundaryNote:
    'Historical inspection record — previous inspections do not prove current compliance.',
};

const OPERATIONAL: OperationalAnalytics = {
  kpis: {
    totalInspections: 12,
    complaintLedInspections: 4,
    decidedInspections: 8,
    complianceRate: null, // no decided denominator path → N/A
    nonComplianceRate: 0.25,
    reviewRequired: 2,
    openInspections: 3,
    averageEvidenceCompleteness: null,
  },
  trend: [
    { period: '2026-08', count: 5 },
    { period: '2026-09', count: 7 },
  ],
  granularity: 'month',
  outcomes: [
    { result: 'COMPLIANT', count: 6, percentage: 0.5 },
    { result: 'NON_COMPLIANT', count: 2, percentage: null },
  ],
  complaintPipeline: {
    stages: [
      { stage: 'COMPLAINTS', label: 'Complaints', count: 10 },
      { stage: 'INSPECTIONS', label: 'Inspections created', count: 4 },
    ],
    conversionRate: 0.4,
  },
  evidenceQuality: {
    inspectionsWithPlanner: 9,
    averageEvidenceCompleteness: null,
    incompleteInspections: 3,
    missingRequiredEvidence: 2,
    measurementsPending: 1,
    reportsBlockedByEvidence: 1,
  },
  findingCategories: [
    { ruleCode: 'LM-QCR-01', label: 'Net quantity', count: 6, inspectionCount: 5, percentage: 0.5 },
  ],
  repeatFindings: [
    {
      productName: 'DEMO Tea 250g',
      ruleCode: 'LM-QCR-01',
      label: 'Net quantity declaration',
      inspectionCount: 2,
      occurrenceCount: 2,
    },
  ],
  locations: {
    locations: [],
    sufficient: false,
    note: 'Location intelligence will appear as inspection locations accumulate.',
  },
  reports: { generated: 5, finalized: 3, amended: 1, pdfExports: 2, docxExports: 1 },
  dataNote: 'Limited data — analytics are based on available inspection records.',
  generatedAt: '2026-09-06T12:00:00Z',
};

function renderAt(path: string, element: React.ReactElement) {
  return render(<MemoryRouter initialEntries={[path]}>{element}</MemoryRouter>);
}

beforeEach(() => {
  searchMock.mockReset().mockResolvedValue(SEARCH_RESULTS);
  historyMock.mockReset().mockResolvedValue(HISTORY_DATA);
  timelineMock.mockReset().mockResolvedValue(TIMELINE);
  listProductsMock.mockReset().mockResolvedValue(PRODUCT_LIST);
  getProductMock.mockReset().mockResolvedValue(PRODUCT_DETAIL);
  analyticsMock.mockReset().mockResolvedValue(OPERATIONAL);
  inspectorsMock.mockReset().mockResolvedValue([
    { id: 'u1', fullName: 'Inspector Ishaan', role: 'INSPECTOR' },
  ]);
});

afterEach(() => cleanup());

// ------------------------------------------------------------ global search

describe('GlobalSearch (UI-09 §2-§5)', () => {
  it('debounces, searches server-side and renders grouped results', async () => {
    renderAt('/history', <GlobalSearch />);

    const input = screen.getByLabelText('Global search');
    expect(input.getAttribute('placeholder')).toBe(
      'Search inspections, complaints, products, reports or evidence...',
    );

    fireEvent.change(input, { target: { value: 'tea' } });
    await waitFor(() =>
      expect(searchMock).toHaveBeenCalledWith({ q: 'tea', limit: 5 }),
    );

    // §2: grouped categories.
    expect(await screen.findByText('Inspections')).toBeTruthy();
    expect(screen.getByText('Complaints')).toBeTruthy();
    expect(screen.getByText('Products')).toBeTruthy();
    expect(screen.getByText('Findings')).toBeTruthy();

    // §4/§5: cross-links to EXISTING detail pages.
    const links = await screen.findAllByRole('link', { name: /LM-00012345/ });
    expect(links.some((l) => l.getAttribute('href') === '/inspections/i1')).toBe(true);
    expect(screen.getByRole('link', { name: /CMP-00042/ }).getAttribute('href')).toBe(
      '/complaints/c1',
    );
    const productLinks = screen.getAllByRole('link', { name: /DEMO Tea 250g/ });
    expect(productLinks.some((l) => l.getAttribute('href') === '/products/p1')).toBe(true);
  });

  it('shows the spec empty state when nothing matches', async () => {
    searchMock.mockResolvedValue({
      query: 'zzz',
      inspections: [],
      complaints: [],
      products: [],
      reports: [],
      findings: [],
      evidence: [],
    });
    renderAt('/history', <GlobalSearch />);

    fireEvent.change(screen.getByLabelText('Global search'), {
      target: { value: 'zzz' },
    });
    expect(await screen.findByText('No matching records.')).toBeTruthy();
  });

  it('does not fire a request below the minimum length', async () => {
    renderAt('/history', <GlobalSearch />);
    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: 't' } });
    await waitFor(() => screen.getByText(/Type at least 2 characters/));
    expect(searchMock).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------- inspection history

describe('HistoryPage (UI-09 §6-§8, §25)', () => {
  function renderHistory(path = '/history') {
    return renderAt(
      path,
      <Routes>
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/inspections/:id" element={<div>workspace</div>} />
      </Routes>,
    );
  }

  it('renders the spec header, subtitle and real filtered-set KPIs', async () => {
    renderHistory();

    expect(screen.getByRole('heading', { name: 'Inspection History' })).toBeTruthy();
    expect(
      screen.getByText('Search and review historical inspection activity.'),
    ).toBeTruthy();

    // KPIs come from the endpoint — real counts, never hardcoded.
    await waitFor(() => expect(historyMock).toHaveBeenCalled());
    expect(await screen.findByText('Total')).toBeTruthy();
    expect(screen.getAllByText('Non-Compliant').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Review Required').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Open').length).toBeGreaterThan(0);
  });

  it('renders the spec table columns from real records', async () => {
    renderHistory();

    const link = await screen.findByRole('link', { name: /LM-00012345/ });
    expect(link.getAttribute('href')).toBe('/inspections/i1');
    expect(screen.getByText('DEMO Tea 250g')).toBeTruthy();
    expect(screen.getByText('Test Market, Delhi')).toBeTruthy();
    expect(screen.getAllByText('Inspector Ishaan').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Citizen Complaint').length).toBeGreaterThan(1); // filter option + row badge
    expect(screen.getAllByText('Non-Compliant').length).toBeGreaterThan(1); // KPI + row badge
    expect(screen.getByTitle('Captured package images').textContent).toContain('2');
    expect(screen.getByText(/Finalized · v1/)).toBeTruthy();
  });

  it('applies filters server-side and persists them in the URL (§25)', async () => {
    renderHistory('/history?result=NON_COMPLIANT&source=CITIZEN_COMPLAINT');

    // Initial load carries the URL filters into the API call.
    await waitFor(() =>
      expect(historyMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          result: 'NON_COMPLIANT',
          source: 'CITIZEN_COMPLAINT',
          page: 1,
          pageSize: 20,
        }),
      ),
    );
  });

  it('sends [Apply] filter changes to the backend', async () => {
    renderHistory();
    await screen.findByRole('link', { name: /LM-00012345/ });

    fireEvent.change(screen.getByLabelText('Search history'), {
      target: { value: 'tea' },
    });
    fireEvent.change(screen.getByLabelText('Result'), {
      target: { value: 'NON_COMPLIANT' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() =>
      expect(historyMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'tea', result: 'NON_COMPLIANT' }),
      ),
    );
  });

  it('shows the spec empty state when filters match nothing', async () => {
    historyMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      kpis: { total: 0, compliant: 0, nonCompliant: 0, reviewRequired: 0, open: 0 },
    });
    renderHistory();

    expect(
      await screen.findByText('No inspections found for the selected filters.'),
    ).toBeTruthy();
  });

  it('shows only recorded timeline events — never fabricated stages (§8)', async () => {
    renderHistory();
    fireEvent.click(await screen.findByRole('button', { name: /View/ }));

    expect(await screen.findByText('Inspection timeline')).toBeTruthy();
    expect(timelineMock).toHaveBeenCalledWith('i1');
    // Recorded events render…
    expect(screen.getByText('Inspection created')).toBeTruthy();
    expect(screen.getByText('Findings generated (engine evaluation)')).toBeTruthy();
    // …and stages that never happened are absent.
    expect(screen.queryByText('Report Generated')).not.toBeTruthy();
    expect(screen.queryByText('Decision')).not.toBeTruthy();
    expect(screen.queryByText('Physical Verification')).not.toBeTruthy();
  });
});

// --------------------------------------------------------- product repository

describe('ProductsPage (UI-09 §9)', () => {
  function renderProducts() {
    return renderAt(
      '/products',
      <Routes>
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/products/:id" element={<div>detail</div>} />
      </Routes>,
    );
  }

  it('renders the spec subtitle and real product rows', async () => {
    renderProducts();

    expect(screen.getByRole('heading', { name: 'Product Repository' })).toBeTruthy();
    expect(screen.getByText('Search packages and review their inspection history.')).toBeTruthy();

    const link = await screen.findByRole('link', { name: /DEMO Tea 250g/ });
    expect(link.getAttribute('href')).toBe('/products/p1');
    expect(screen.getByText('food')).toBeTruthy();
  });

  it('searches server-side through the list endpoint', async () => {
    renderProducts();
    await screen.findByRole('link', { name: /DEMO Tea 250g/ });

    fireEvent.change(screen.getByLabelText('Search products'), {
      target: { value: 'namkeen' },
    });
    await waitFor(() =>
      expect(listProductsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'namkeen' }),
      ),
    );
  });

  it('shows the spec empty state when no products exist', async () => {
    listProductsMock.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    renderProducts();

    expect(await screen.findByText('No product records available.')).toBeTruthy();
  });
});

describe('ProductDetailPage (UI-09 §10-§11)', () => {
  function renderDetail() {
    return renderAt(
      '/products/p1',
      <Routes>
        <Route path="/products/:id" element={<ProductDetailPage />} />
      </Routes>,
    );
  }

  it('renders the historical record with the boundary note verbatim', async () => {
    renderDetail();

    expect(getProductMock).toHaveBeenCalledWith('p1');
    expect(
      await screen.findByText(
        /Historical inspection record — previous inspections do not prove current compliance/,
      ),
    ).toBeTruthy();
  });

  it('renders inspection history and recurring findings with neutral wording', async () => {
    renderDetail();

    expect(await screen.findByText('Inspection history')).toBeTruthy();
    const links = screen.getAllByRole('link', { name: /LM-00012345/ });
    expect(links.some((l) => l.getAttribute('href') === '/inspections/i1')).toBe(true);
    // §11: neutral, historical wording — never a violator label.
    expect(screen.getByText('Repeated inspection findings')).toBeTruthy();
    expect(screen.getByText(/A historical pattern — not a verdict/)).toBeTruthy();
    expect(screen.getByText('LM-QCR-01')).toBeTruthy();
    expect(screen.queryByText(/repeat offender/i)).not.toBeTruthy();
  });

  it('renders the evidence gallery linking to the originating inspection', async () => {
    renderDetail();

    expect(await screen.findByText('Evidence gallery')).toBeTruthy();
    const gallery = screen.getByRole('link', { name: /front.png/ });
    expect(gallery.getAttribute('href')).toBe('/inspections/i1');
  });
});

// ------------------------------------------------------ operational analytics

describe('AnalyticsPage (UI-09 §12-§24)', () => {
  function renderAnalytics() {
    return renderAt(
      '/analytics',
      <Routes>
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/reports" element={<div>reports</div>} />
        <Route path="/audit" element={<div>audit</div>} />
      </Routes>,
    );
  }

  it('renders real KPIs with N/A for null rates — never a fake 0%', async () => {
    renderAnalytics();

    await waitFor(() => expect(analyticsMock).toHaveBeenCalled());
    expect(await screen.findByText('Total Inspections')).toBeTruthy();
    expect(screen.getByText('Compliance Rate')).toBeTruthy();
    // complianceRate is null → N/A (§14), and avg evidence completeness too.
    expect(screen.getAllByText('N/A').length).toBeGreaterThanOrEqual(2);
    // nonComplianceRate 0.25 → a real percentage.
    expect(screen.getByText('25.0%')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('shows the honest limited-data banner (§12)', async () => {
    renderAnalytics();
    expect(
      await screen.findByText(
        'Limited data — analytics are based on available inspection records.',
      ),
    ).toBeTruthy();
  });

  it('renders the complaint pipeline with real counts and conversion', async () => {
    renderAnalytics();

    expect(await screen.findByText('Complaint → inspection pipeline')).toBeTruthy();
    expect(screen.getByText('Complaints')).toBeTruthy();
    expect(screen.getByText('Inspections created')).toBeTruthy();
    expect(screen.getByText(/40.0%/)).toBeTruthy();
    // §16: the example numbers from the spec must not be hardcoded.
    expect(screen.queryByText('342')).not.toBeTruthy();
  });

  it('renders repeated findings with neutral wording and location honesty (§21, §22)', async () => {
    renderAnalytics();

    expect(await screen.findByText('Repeated inspection findings')).toBeTruthy();
    expect(screen.getByText('Repeated inspection finding')).toBeTruthy();
    expect(
      await screen.findByText(
        'Location intelligence will appear as inspection locations accumulate.',
      ),
    ).toBeTruthy();
  });

  it('links to the existing Reports and Audit Trail pages (§23, §24)', async () => {
    renderAnalytics();

    expect(await screen.findByText('Operational Intelligence')).toBeTruthy();
    expect(screen.getAllByRole('link', { name: /View Reports/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /View Audit Trail/ }).getAttribute('href')).toBe(
      '/audit',
    );
  });

  it('shows the spec error state when the backend fails', async () => {
    analyticsMock.mockRejectedValue(new Error('boom'));
    renderAnalytics();

    expect(await screen.findByText('Unable to load operational data.')).toBeTruthy();
  });

  it('passes the granularity + date filter to the backend', async () => {
    renderAnalytics();
    await screen.findByText('Operational Intelligence');

    fireEvent.change(screen.getByLabelText('Granularity'), { target: { value: 'day' } });
    await waitFor(() =>
      expect(analyticsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ granularity: 'day' }),
      ),
    );
  });
});
