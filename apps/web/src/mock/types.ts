/**
 * Presentation view-models for the demo data layer.
 *
 * These are FRONTEND presentation shapes (a Risk Score, a Review-queue row, an
 * evidence chain node). They are deliberately separate from the wire contracts
 * in `@legalmet/types` — anything that maps to a real backend entity uses the
 * shared type; anything that is a UI-only convenience lives here. All instances
 * are DEMO data and must be rendered with a "DEMO DATA — NOT LEGAL ADVICE"
 * marker where regulatory content is involved.
 */
import type { BoundingBox, ComplianceStatus, FieldType, Inspection } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

export type RiskLevel = 'HIGH' | 'MEDIUM' | 'LOW';

export type ValidationResult = 'PASS' | 'FAIL' | 'INCONCLUSIVE';

/** A rule reference — DEMO only. `code`/`source` are placeholders, not real citations. */
export interface RuleRef {
  code: string;
  title: string;
  requirement: string;
  versionLabel: string;
  effectiveFrom: string;
  source: string;
}

/** One node in the human-readable evidence chain. */
export interface ChainNode {
  type:
    | 'PACKAGE'
    | 'IMAGE'
    | 'IMAGE_REGION'
    | 'EXTRACTED_FIELD'
    | 'RULE'
    | 'VALIDATION_RESULT'
    | 'FINDING';
  label: string;
  detail?: string;
}

/** Region drawn on the package image viewer, coloured by finding tone. */
export interface ViewerRegion {
  id: string;
  fieldType: FieldType;
  label: string;
  bbox: BoundingBox;
  tone: Tone;
}

/** A detected declaration row in the intelligence panel. */
export interface DetectedDeclaration {
  field: FieldType;
  value: string;
  status: ComplianceStatus;
  confidence: number;
  regionId?: string;
}

export interface QualityMetric {
  label: string;
  score: number;
  status: string;
}

/** Everything the Inspection Workspace + WHY panel needs, fully linked. */
export interface FindingView {
  id: string;
  inspectionId: string;
  title: string;
  fieldType: FieldType | null;
  status: ComplianceStatus;
  confidence: number;
  risk: RiskLevel;
  /** Human-readable "why this finding was created". */
  rationale: string;
  isReviewed: boolean;
  reviewStatus?: ComplianceStatus | null;
  detectedValue?: string;
  regionId?: string;
  rule?: RuleRef;
  expected?: string;
  detected?: string;
  validationResult?: ValidationResult;
  chain: ChainNode[];
  createdAt: string;
}

export interface InspectionDetail {
  inspection: Inspection;
  imageRegions: ViewerRegion[];
  quality: QualityMetric[];
  qualityScore: number;
  declarations: DetectedDeclaration[];
  findings: FindingView[];
  /** Inspection-assistance metric (0..100) — NOT legally authoritative. */
  complianceScore: number;
}

export interface RiskCase {
  inspectionId: string;
  product: string;
  category: string;
  risk: RiskLevel;
  riskScore: number;
  reason: string;
  confidence: number;
  finding: string;
  recommendedAction: string;
}

export interface ReviewQueueItem {
  findingId: string;
  inspectionId: string;
  product: string;
  finding: string;
  status: ComplianceStatus;
  confidence: number;
  risk: RiskLevel;
  reason: string;
  createdAt: string;
  assignedTo: string;
}

export interface ReportItem {
  id: string;
  type: 'INSPECTION' | 'BATCH';
  title: string;
  inspectionId?: string;
  createdAt: string;
  status: 'DRAFT' | 'FINALIZED';
  inspector: string;
}

export interface ActivityPoint {
  label: string;
  scanned: number;
  flagged: number;
}

export interface CategoryStat {
  category: string;
  total: number;
  violationRate: number;
  reviewRate: number;
  confidence: number;
}

export interface EvidenceItem {
  id: string;
  inspectionId: string;
  product: string;
  fieldType: FieldType;
  value: string;
  confidence: number;
  finding: string;
  status: ComplianceStatus;
  region: BoundingBox;
}
