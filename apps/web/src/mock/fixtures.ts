/**
 * DEMO fixtures for METRASIGHT (SIH26034).
 *
 * ⚠ DEMO DATA — NOT LEGAL ADVICE. Every regulation/rule below is a clearly
 * labelled placeholder. Rule codes and sources are fictional and must NOT be
 * presented as official Legal Metrology citations. `isDemo: true` throughout.
 *
 * All data is shaped to the shared `@legalmet/types` contracts so the same UI
 * can later be pointed at real endpoints with no component changes.
 */
import type {
  FindingCounts,
  Regulation,
  RegulationVersion,
  Rule,
  User,
} from '@legalmet/types';

import type { FindingView } from './types';

/* -------------------------------------------------------------------------- */
/* Users                                                                      */
/* -------------------------------------------------------------------------- */
export const users: User[] = [
  {
    id: 'usr-anita',
    email: 'anita.rao@legalmet.local',
    fullName: 'Anita Rao',
    role: 'INSPECTOR',
    isActive: true,
    createdAt: '2026-01-12T09:00:00Z',
  },
  {
    id: 'usr-rahul',
    email: 'rahul.verma@legalmet.local',
    fullName: 'Rahul Verma',
    role: 'SUPERVISOR',
    isActive: true,
    createdAt: '2025-11-02T09:00:00Z',
  },
  {
    id: 'usr-priya',
    email: 'priya.menon@legalmet.local',
    fullName: 'Priya Menon',
    role: 'AUDITOR',
    isActive: true,
    createdAt: '2025-10-20T09:00:00Z',
  },
  {
    id: 'usr-nair',
    email: 's.nair@legalmet.local',
    fullName: 'Dr. S. Nair',
    role: 'ADMIN',
    isActive: true,
    createdAt: '2025-09-01T09:00:00Z',
  },
];

export const currentUser: User = users[0];

export const usersById: Record<string, User> = Object.fromEntries(
  users.map((u) => [u.id, u]),
);

export function inspectorName(id?: string | null): string {
  return (id && usersById[id]?.fullName) || 'Unassigned';
}

/* -------------------------------------------------------------------------- */
/* Regulatory knowledge (DEMO)                                                */
/* -------------------------------------------------------------------------- */
export const regulation: Regulation = {
  id: 'reg-lmpc',
  code: 'DEMO-LMPC',
  title: 'Packaged Commodity Declarations — DEMO dataset',
  jurisdiction: 'India (DEMO)',
  authority: 'DEMO Authority — placeholder, not an official body',
  description:
    'Placeholder regulatory dataset modelling mandatory pre-packaged commodity declarations for demonstration of the version-aware rule engine. Not verified legal content.',
  officialSourceUrl: null,
  isDemo: true,
  documentType: 'OTHER',
  createdAt: '2024-01-01T00:00:00Z',
};

export const regulationVersions: RegulationVersion[] = [
  {
    id: 'rv-1',
    regulationId: 'reg-lmpc',
    versionLabel: 'Demo v1.0',
    status: 'SUPERSEDED',
    effectiveFrom: '2019-01-01',
    effectiveUntil: '2022-03-31',
    amendmentOfId: null,
    sourceDocumentRef: 'DEMO-DOC-A',
    isDemo: true,
    createdAt: '2019-01-01T00:00:00Z',
  },
  {
    id: 'rv-2',
    regulationId: 'reg-lmpc',
    versionLabel: 'Demo v2.0 (Amendment)',
    status: 'SUPERSEDED',
    effectiveFrom: '2022-04-01',
    effectiveUntil: '2023-12-31',
    amendmentOfId: 'rv-1',
    sourceDocumentRef: 'DEMO-DOC-B',
    isDemo: true,
    createdAt: '2022-04-01T00:00:00Z',
  },
  {
    id: 'rv-3',
    regulationId: 'reg-lmpc',
    versionLabel: 'Demo v3.0',
    status: 'ACTIVE',
    effectiveFrom: '2024-01-01',
    effectiveUntil: null,
    amendmentOfId: 'rv-2',
    sourceDocumentRef: 'DEMO-DOC-C',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
];

export const rules: Rule[] = [
  {
    id: 'rule-mrp',
    regulationVersionId: 'rv-3',
    ruleCode: 'DR-MRP-01',
    title: 'Maximum Retail Price declaration',
    requirementSummary:
      'A retail sale price must be declared legibly and prominently, expressed as inclusive of all taxes.',
    validationLogicRef: 'validators.mrp_present_and_inclusive',
    evidenceRequirement: 'A detected MRP text region with a normalised currency value.',
    status: 'ACTIVE',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-nq',
    regulationVersionId: 'rv-3',
    ruleCode: 'DR-NQ-01',
    title: 'Net quantity declaration',
    requirementSummary:
      'Net quantity must be declared in standard units using the metric system.',
    validationLogicRef: 'validators.net_quantity_standard_unit',
    evidenceRequirement: 'A detected net-quantity region with a value and a recognised unit.',
    status: 'ACTIVE',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-coo',
    regulationVersionId: 'rv-3',
    ruleCode: 'DR-COO-01',
    title: 'Country of origin declaration',
    requirementSummary:
      'Country of origin must be declared for the packaged commodity where applicable.',
    validationLogicRef: 'validators.country_of_origin_present',
    evidenceRequirement: 'A detected country-of-origin region.',
    status: 'ACTIVE',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-mfg',
    regulationVersionId: 'rv-3',
    ruleCode: 'DR-MFG-01',
    title: 'Manufacturer / packer details',
    requirementSummary:
      'Name and complete address of the manufacturer or packer must be declared.',
    validationLogicRef: 'validators.manufacturer_details_complete',
    evidenceRequirement: 'A detected manufacturer/packer region with name and address text.',
    status: 'ACTIVE',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-date',
    regulationVersionId: 'rv-3',
    ruleCode: 'DR-DATE-01',
    title: 'Date of manufacture / packing',
    requirementSummary: 'The month and year of manufacture or packing must be declared.',
    validationLogicRef: 'validators.packing_date_present',
    evidenceRequirement: 'A detected date region parseable to a month/year.',
    status: 'ACTIVE',
    isDemo: true,
    createdAt: '2024-01-01T00:00:00Z',
  },
];

export const rulesById: Record<string, Rule> = Object.fromEntries(rules.map((r) => [r.id, r]));

/** Rule-reference builders keep DEMO rule metadata attached to findings. */
export const RULE_REFS = {
  mrp: {
    code: 'DR-MRP-01',
    title: 'Maximum Retail Price declaration',
    requirement:
      'A retail sale price must be declared legibly and prominently, inclusive of all taxes.',
    versionLabel: 'Demo v3.0',
    effectiveFrom: '2024-01-01',
    source: 'DEMO dataset — not an official citation',
  },
  nq: {
    code: 'DR-NQ-01',
    title: 'Net quantity declaration',
    requirement: 'Net quantity must be declared in standard metric units.',
    versionLabel: 'Demo v3.0',
    effectiveFrom: '2024-01-01',
    source: 'DEMO dataset — not an official citation',
  },
  coo: {
    code: 'DR-COO-01',
    title: 'Country of origin declaration',
    requirement: 'Country of origin must be declared where applicable.',
    versionLabel: 'Demo v3.0',
    effectiveFrom: '2024-01-01',
    source: 'DEMO dataset — not an official citation',
  },
  mfg: {
    code: 'DR-MFG-01',
    title: 'Manufacturer / packer details',
    requirement: 'Name and complete address of manufacturer or packer must be declared.',
    versionLabel: 'Demo v3.0',
    effectiveFrom: '2024-01-01',
    source: 'DEMO dataset — not an official citation',
  },
  date: {
    code: 'DR-DATE-01',
    title: 'Date of manufacture / packing',
    requirement: 'Month and year of manufacture or packing must be declared.',
    versionLabel: 'Demo v3.0',
    effectiveFrom: '2024-01-01',
    source: 'DEMO dataset — not an official citation',
  },
} as const;

/* -------------------------------------------------------------------------- */
/* Finding-counts + score helpers                                             */
/* -------------------------------------------------------------------------- */
export function countsFrom(findings: Pick<FindingView, 'status'>[]): FindingCounts {
  const c: FindingCounts = {
    total: findings.length,
    compliant: 0,
    potentialViolation: 0,
    reviewRequired: 0,
    notApplicable: 0,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  };
  for (const f of findings) {
    if (f.status === 'COMPLIANT') c.compliant += 1;
    else if (f.status === 'POTENTIAL_VIOLATION') c.potentialViolation += 1;
    else if (f.status === 'REVIEW_REQUIRED') c.reviewRequired += 1;
    else if (f.status === 'NOT_APPLICABLE') c.notApplicable += 1;
    else if (f.status === 'LOW_CONFIDENCE') c.lowConfidence += 1;
    else if (f.status === 'IMAGE_QUALITY_INSUFFICIENT') c.imageQualityInsufficient += 1;
  }
  return c;
}

/** Assistance metric (0..100), NOT legally authoritative. */
export function assistanceScore(c: FindingCounts): number {
  const applicable = c.total - c.notApplicable;
  if (applicable <= 0) return 100;
  return Math.round(((c.compliant + 0.5 * c.reviewRequired) / applicable) * 100);
}
