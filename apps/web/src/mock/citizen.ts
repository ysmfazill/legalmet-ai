/**
 * DEMO complaint & citizen data (SIH26034).
 *
 * ⚠ DEMO DATA — NOT LEGAL ADVICE. There is NO complaint backend yet (no
 * model/router/endpoint exists in services/api), so this module is the
 * clearly-labelled demo seam for the Complaint Management and Citizen Mode
 * experiences, exactly like the rest of mock/. Conversion of a complaint into
 * a real inspection deep-links into the REAL New Inspection flow; everything
 * here is presentation-only.
 *
 * Wording contract (important): citizen-facing copy says "possible issue" /
 * "suspected issue" — NEVER "violation confirmed" — because the final legal
 * determination belongs to the Legal Metrology authority.
 */
import type { Tone } from '@legalmet/config';

/** Department complaint lifecycle. DEMO vocabulary mirroring common dept flows. */
export type ComplaintStatus =
  | 'NEW'
  | 'UNDER_REVIEW'
  | 'ACCEPTED'
  | 'ASSIGNED'
  | 'INSPECTION_SCHEDULED'
  | 'INSPECTION_COMPLETED'
  | 'ACTION_TAKEN'
  | 'CLOSED';

export const COMPLAINT_STATUS_ORDER: ComplaintStatus[] = [
  'NEW',
  'UNDER_REVIEW',
  'ACCEPTED',
  'ASSIGNED',
  'INSPECTION_SCHEDULED',
  'INSPECTION_COMPLETED',
  'ACTION_TAKEN',
  'CLOSED',
];

export const COMPLAINT_STATUS_META: Record<ComplaintStatus, { label: string; tone: Tone; hint: string }> = {
  NEW: { label: 'New', tone: 'info', hint: 'Received, not yet triaged' },
  UNDER_REVIEW: { label: 'Under review', tone: 'warning', hint: 'Department is evaluating the report' },
  ACCEPTED: { label: 'Accepted', tone: 'info', hint: 'Valid complaint, awaiting assignment' },
  ASSIGNED: { label: 'Assigned', tone: 'warning', hint: 'An inspector has been assigned' },
  INSPECTION_SCHEDULED: { label: 'Inspection scheduled', tone: 'info', hint: 'Field inspection is booked' },
  INSPECTION_COMPLETED: { label: 'Inspection completed', tone: 'info', hint: 'Field inspection finished' },
  ACTION_TAKEN: { label: 'Action taken', tone: 'positive', hint: 'Enforcement action recorded' },
  CLOSED: { label: 'Closed', tone: 'neutral', hint: 'Complaint resolved / archived' },
};

/** How strong the citizen-supplied evidence is (guides triage). */
export type EvidenceQuality = 'PHOTO' | 'PHOTO_AND_DETAILS' | 'DETAILS_ONLY';

export const EVIDENCE_QUALITY_META: Record<EvidenceQuality, { label: string; tone: Tone; hint: string }> = {
  PHOTO: { label: 'Photo evidence', tone: 'positive', hint: 'Clear package photo attached' },
  PHOTO_AND_DETAILS: { label: 'Photo + details', tone: 'positive', hint: 'Photo plus batch/location details' },
  DETAILS_ONLY: { label: 'Details only', tone: 'warning', hint: 'No photo — verification needed' },
};

export type ComplaintRisk = 'HIGH' | 'MEDIUM' | 'LOW';

export interface Complaint {
  id: string;
  /** Reference number shown to the department. */
  referenceNo: string;
  product: string;
  category: string;
  /** Where the package was purchased/observed. */
  location: string;
  district: string;
  /** Short summary of the reported issue. */
  issue: string;
  /** Suspected declaration problem, in citizen-readable words. */
  suspectedIssue: string;
  status: ComplaintStatus;
  evidenceQuality: EvidenceQuality;
  risk: ComplaintRisk;
  submittedAt: string;
  /** Citizen reporter — pseudonymous demo identity. */
  reporter: string;
  /** Assigned inspector (null until ASSIGNED). */
  assignedInspector: string | null;
  /** Linked inspection created from this complaint (null until converted). */
  linkedInspectionId: string | null;
  /** Whether a package photo is attached (demo flag). */
  hasPhoto: boolean;
}

export const complaints: Complaint[] = [
  {
    id: 'cpl-001',
    referenceNo: 'CMP-2026-0141',
    product: 'Sunrise Turmeric Powder 500 g',
    category: 'Food',
    location: 'Mart Bazaar, Jayanagar 4th Block, Bengaluru',
    district: 'Bengaluru South',
    issue: 'MRP printed on two stickers — different prices',
    suspectedIssue: 'MRP declaration may be tampered or duplicated',
    status: 'UNDER_REVIEW',
    evidenceQuality: 'PHOTO_AND_DETAILS',
    risk: 'HIGH',
    submittedAt: '2026-08-28T10:20:00Z',
    reporter: 'Citizen #A-114',
    assignedInspector: null,
    linkedInspectionId: null,
    hasPhoto: true,
  },
  {
    id: 'cpl-002',
    referenceNo: 'CMP-2026-0142',
    product: 'AquaPure Bottled Water 1 L',
    category: 'Beverages',
    location: 'Railway station kiosk, Pune',
    district: 'Pune City',
    issue: 'Bottle felt under-filled compared to declared 1 litre',
    suspectedIssue: 'Net quantity possibly short of declaration',
    status: 'ASSIGNED',
    evidenceQuality: 'PHOTO',
    risk: 'MEDIUM',
    submittedAt: '2026-08-26T16:05:00Z',
    reporter: 'Citizen #B-209',
    assignedInspector: 'Anita Rao',
    linkedInspectionId: null,
    hasPhoto: true,
  },
  {
    id: 'cpl-003',
    referenceNo: 'CMP-2026-0143',
    product: 'GlowFair Face Cream 80 g',
    category: 'Cosmetics',
    location: 'Sharma General Store, Karol Bagh, Delhi',
    district: 'Central Delhi',
    issue: 'No manufacturing date visible on the carton',
    suspectedIssue: 'Mandatory date declaration may be missing',
    status: 'ACCEPTED',
    evidenceQuality: 'PHOTO',
    risk: 'MEDIUM',
    submittedAt: '2026-08-25T11:40:00Z',
    reporter: 'Citizen #C-057',
    assignedInspector: null,
    linkedInspectionId: null,
    hasPhoto: true,
  },
  {
    id: 'cpl-004',
    referenceNo: 'CMP-2026-0144',
    product: 'Daawat Basmati Rice 5 kg',
    category: 'Food',
    location: 'Online order, delivered in Hyderabad',
    district: 'Hyderabad',
    issue: 'Packaging says "Farm Fresh" but no packer address',
    suspectedIssue: 'Manufacturer/packer declaration may be incomplete',
    status: 'NEW',
    evidenceQuality: 'DETAILS_ONLY',
    risk: 'LOW',
    submittedAt: '2026-08-30T09:15:00Z',
    reporter: 'Citizen #D-311',
    assignedInspector: null,
    linkedInspectionId: null,
    hasPhoto: false,
  },
  {
    id: 'cpl-005',
    referenceNo: 'CMP-2026-0145',
    product: 'Chai Point Tea Dust 250 g',
    category: 'Beverages',
    location: 'D Mart, Whitefield, Bengaluru',
    district: 'Bengaluru East',
    issue: 'No country of origin printed anywhere on pack',
    suspectedIssue: 'Country-of-origin declaration may be missing',
    status: 'INSPECTION_SCHEDULED',
    evidenceQuality: 'PHOTO_AND_DETAILS',
    risk: 'HIGH',
    submittedAt: '2026-08-22T14:50:00Z',
    reporter: 'Citizen #A-114',
    assignedInspector: 'Rahul Verma',
    linkedInspectionId: null,
    hasPhoto: true,
  },
  {
    id: 'cpl-006',
    referenceNo: 'CMP-2026-0146',
    product: 'Kichdi Rava 1 kg',
    category: 'Food',
    location: 'Local mill outlet, Mysuru',
    district: 'Mysuru',
    issue: 'Price charged above printed MRP',
    suspectedIssue: 'MRP overcharging at retail point',
    status: 'INSPECTION_COMPLETED',
    evidenceQuality: 'PHOTO',
    risk: 'MEDIUM',
    submittedAt: '2026-08-18T18:30:00Z',
    reporter: 'Citizen #E-083',
    assignedInspector: 'Anita Rao',
    linkedInspectionId: 'INS-1024',
    hasPhoto: true,
  },
  {
    id: 'cpl-007',
    referenceNo: 'CMP-2026-0147',
    product: 'SweetLeaf Stevia Sachets',
    category: 'Food',
    location: 'Aashirwad Supermarket, Indiranagar, Bengaluru',
    district: 'Bengaluru South',
    issue: 'Net quantity printed only on the back, very small text',
    suspectedIssue: 'Net quantity readability may not meet requirements',
    status: 'CLOSED',
    evidenceQuality: 'PHOTO_AND_DETAILS',
    risk: 'LOW',
    submittedAt: '2026-08-10T12:00:00Z',
    reporter: 'Citizen #F-142',
    assignedInspector: 'Rahul Verma',
    linkedInspectionId: 'INS-1021',
    hasPhoto: true,
  },
  {
    id: 'cpl-008',
    referenceNo: 'CMP-2026-0148',
    product: 'HomeFresh Atta 10 kg',
    category: 'Food',
    location: 'Big Bazaar, Lucknow',
    district: 'Lucknow',
    issue: 'Consumer care number printed is always busy',
    suspectedIssue: 'Consumer care contact may be non-functional',
    status: 'ACTION_TAKEN',
    evidenceQuality: 'DETAILS_ONLY',
    risk: 'MEDIUM',
    submittedAt: '2026-08-05T09:00:00Z',
    reporter: 'Citizen #G-020',
    assignedInspector: 'Anita Rao',
    linkedInspectionId: 'INS-1018',
    hasPhoto: false,
  },
];

/* -------------------------------------------------------------------------- */
/* Citizen mode — scan results & my reports                                    */
/* -------------------------------------------------------------------------- */

/** A single suspected issue found in a citizen scan (demo perception output). */
export interface CitizenFinding {
  id: string;
  /** Citizen-readable issue title. */
  title: string;
  /** Why this may matter to a consumer. */
  whyItMatters: string;
  /** What was detected on the label (plain words). */
  detected: string;
  /** The declaration that seems affected. */
  declaration: string;
  /** AI confidence in the reading — NOT legal certainty. */
  confidence: number;
  /** Whether image evidence backs the reading. */
  hasImageEvidence: boolean;
}

/** Result of one citizen scan (SCAN → DETECT → REPORT). */
export interface CitizenScanResult {
  id: string;
  product: string;
  scannedAt: string;
  /** Overall outcome in citizen language. */
  outcome: 'POSSIBLE_ISSUE' | 'NO_OBVIOUS_ISSUE' | 'UNCLEAR_IMAGE';
  outcomeLabel: string;
  findings: CitizenFinding[];
}

export const citizenScanDemo: CitizenScanResult = {
  id: 'cscan-001',
  product: 'Sunrise Turmeric Powder 500 g',
  scannedAt: '2026-08-28T10:18:00Z',
  outcome: 'POSSIBLE_ISSUE',
  outcomeLabel: 'Possible issue detected',
  findings: [
    {
      id: 'cf-001',
      title: 'MRP appears on two stickers with different prices',
      whyItMatters:
        'The Maximum Retail Price is a mandatory declaration. Two different prices can mean an old price was covered up — you may be overcharged.',
      detected: 'Two sticker layers read: ₹86 and ₹95',
      declaration: 'MRP (Maximum Retail Price)',
      confidence: 88,
      hasImageEvidence: true,
    },
    {
      id: 'cf-002',
      title: 'Net quantity text is very small',
      whyItMatters:
        'The net quantity tells you how much product you are buying. It must be easy to read on the front of the pack.',
      detected: '"500 g" detected in small print, bottom-left of back panel',
      declaration: 'Net quantity',
      confidence: 74,
      hasImageEvidence: true,
    },
  ],
};

/** Citizen's previously submitted reports (demo). */
export interface CitizenReport {
  id: string;
  referenceNo: string;
  product: string;
  submittedAt: string;
  status: ComplaintStatus;
  /** One-line citizen-friendly status explanation. */
  statusNote: string;
}

export const citizenMyReports: CitizenReport[] = [
  {
    id: 'cr-001',
    referenceNo: 'CMP-2026-0141',
    product: 'Sunrise Turmeric Powder 500 g',
    submittedAt: '2026-08-28T10:20:00Z',
    status: 'UNDER_REVIEW',
    statusNote: 'The department is reviewing your report.',
  },
  {
    id: 'cr-002',
    referenceNo: 'CMP-2026-0132',
    product: 'Mithai Sweets Box 750 g',
    submittedAt: '2026-08-14T15:45:00Z',
    status: 'ACTION_TAKEN',
    statusNote: 'The department inspected and action was recorded.',
  },
  {
    id: 'cr-003',
    referenceNo: 'CMP-2026-0119',
    product: 'ColdPress Cooking Oil 1 L',
    submittedAt: '2026-07-30T11:10:00Z',
    status: 'CLOSED',
    statusNote: 'Your report was reviewed and closed.',
  },
];

/** Nearby/submitted complaints in the citizen's area (demo). */
export interface NearbyComplaint {
  id: string;
  area: string;
  district: string;
  productCategory: string;
  issue: string;
  reports: number;
  lastReportedAt: string;
}

export const nearbyComplaints: NearbyComplaint[] = [
  {
    id: 'nc-001',
    area: 'Jayanagar 4th Block',
    district: 'Bengaluru South',
    productCategory: 'Food',
    issue: 'Duplicate MRP stickers',
    reports: 6,
    lastReportedAt: '2026-08-28T10:20:00Z',
  },
  {
    id: 'nc-002',
    area: 'Whitefield',
    district: 'Bengaluru East',
    productCategory: 'Beverages',
    issue: 'Missing country of origin',
    reports: 4,
    lastReportedAt: '2026-08-26T09:00:00Z',
  },
  {
    id: 'nc-003',
    area: 'Indiranagar',
    district: 'Bengaluru South',
    productCategory: 'Food',
    issue: 'Small net quantity text',
    reports: 2,
    lastReportedAt: '2026-08-20T17:30:00Z',
  },
];
