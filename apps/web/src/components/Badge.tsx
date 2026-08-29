import type { ReactNode } from 'react';

import {
  APPLICABILITY_OUTCOME_META,
  COMPLIANCE_STATUS_META,
  ENGINE_FINDING_STATUS_META,
  EVALUATION_STATUS_META,
  EXTRACTION_STATUS_META,
  IMAGE_PROCESSING_STATUS_META,
  IMAGE_QUALITY_GRADE_META,
  INSPECTION_STATUS_META,
  IMAGE_QUALITY_META,
  PACKAGE_STATUS_META,
  PROCESSING_RUN_STATUS_META,
  USER_ROLE_META,
  VERIFICATION_STATUS_META,
} from '@legalmet/config';
import type { Tone } from '@legalmet/config';
import type {
  ApplicabilityOutcome,
  ComplianceStatus,
  EngineFindingStatus,
  EvaluationStatus,
  ExtractionStatus,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  InspectionStatus,
  PackageStatus,
  ProcessingRunStatus,
  UserRole,
  VerificationStatus,
} from '@legalmet/types';

import { CONFIDENCE_TONE, confidenceBand, formatPercent } from '../lib/format';
import type { RiskLevel } from '../mock/types';
import { cn } from '../lib/cn';
import { Icon } from './Icon';

/* -------------------------------------------------------------------------- */
/* Generic badge                                                              */
/* -------------------------------------------------------------------------- */
interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  outline?: boolean;
  square?: boolean;
  title?: string;
  className?: string;
}

export function Badge({ tone, children, dot, outline, square, title, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'badge',
        tone && `badge--${tone}`,
        outline && 'badge--outline',
        square && 'badge--square',
        className,
      )}
      title={title}
    >
      {dot && <span className="badge__dot" aria-hidden />}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Domain badges                                                              */
/* -------------------------------------------------------------------------- */
export function StatusBadge({ status, dot = true }: { status: ComplianceStatus; dot?: boolean }) {
  const meta = COMPLIANCE_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot={dot} title={meta.description}>
      {meta.label}
    </Badge>
  );
}

export function InspectionStatusBadge({ status }: { status: InspectionStatus }) {
  const meta = INSPECTION_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

export function ImageQualityBadge({ status }: { status: ImageQualityStatus }) {
  const meta = IMAGE_QUALITY_META[status];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

/**
 * Image *usability* grade — NOT an AI-confidence or compliance judgement.
 * The title spells that out so the badge can never be misread.
 */
export function ImageQualityGradeBadge({ grade }: { grade: ImageQualityGrade }) {
  const meta = IMAGE_QUALITY_GRADE_META[grade];
  return (
    <Badge tone={meta.tone} title={meta.description ?? 'Image usability grade (not a compliance result)'}>
      {meta.label}
    </Badge>
  );
}

export function ImageProcessingBadge({ status }: { status: ImageProcessingStatus }) {
  const meta = IMAGE_PROCESSING_STATUS_META[status];
  return (
    <Badge tone={meta.tone} outline title={meta.description}>
      {meta.label}
    </Badge>
  );
}

export function PackageStatusBadge({ status }: { status: PackageStatus }) {
  const meta = PACKAGE_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

export function RoleBadge({ role }: { role: UserRole }) {
  const meta = USER_ROLE_META[role];
  return (
    <Badge tone={meta.tone} outline>
      {meta.label}
    </Badge>
  );
}

/* -------------------------------------------------------------------------- */
/* Perception (Prompt 4)                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Perception processing-run status. Describes what the pipeline DID to the
 * image — never a compliance verdict. The title tooltip spells that out.
 */
export function ProcessingRunBadge({ status }: { status: ProcessingRunStatus }) {
  const meta = PROCESSING_RUN_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot title={meta.description ?? 'Perception run status (not a compliance result)'}>
      {meta.label}
    </Badge>
  );
}

/**
 * Per-field perception outcome — DETECTED / REVIEW_REQUIRED / NOT_EXTRACTED.
 * This is what the extractor saw, not what the law requires.
 */
export function ExtractionStatusBadge({ status }: { status: ExtractionStatus }) {
  const meta = EXTRACTION_STATUS_META[status];
  return (
    <Badge tone={meta.tone} outline title={meta.description ?? 'Perception outcome (not a compliance result)'}>
      {meta.label}
    </Badge>
  );
}

/**
 * Verification state of a regulatory SOURCE (Prompt 5) — whether its content
 * was checked against an official publication. Explicitly NOT OCR confidence
 * and NOT a compliance verdict.
 */
export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const meta = VERIFICATION_STATUS_META[status];
  return (
    <Badge
      tone={meta.tone}
      dot
      title={meta.description ?? 'Source verification state (not OCR confidence)'}
    >
      {meta.label}
    </Badge>
  );
}

/**
 * Deterministic ENGINE finding status (Prompt 6). A system decision-support
 * output — the badge's tooltip reiterates that this is not an enforcement
 * determination.
 */
export function EngineFindingBadge({ status }: { status: EngineFindingStatus }) {
  const meta = ENGINE_FINDING_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot title={meta.description}>
      {meta.label}
    </Badge>
  );
}

/** Lifecycle status of one compliance-engine evaluation run (Prompt 6). */
export function EvaluationStatusBadge({ status }: { status: EvaluationStatus }) {
  const meta = EVALUATION_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot title={meta.description}>
      {meta.label}
    </Badge>
  );
}

/** Deterministic applicability outcome for one finding (Prompt 6). */
export function ApplicabilityBadge({ outcome }: { outcome: ApplicabilityOutcome }) {
  const meta = APPLICABILITY_OUTCOME_META[outcome];
  return (
    <Badge tone={meta.tone} title={meta.description}>
      {meta.label}
    </Badge>
  );
}

export const RISK_META: Record<RiskLevel, { label: string; tone: Tone }> = {
  HIGH: { label: 'High', tone: 'critical' },
  MEDIUM: { label: 'Medium', tone: 'warning' },
  LOW: { label: 'Low', tone: 'neutral' },
};

export function RiskBadge({ risk, withLabel = true }: { risk: RiskLevel; withLabel?: boolean }) {
  const meta = RISK_META[risk];
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
      {withLabel ? ' risk' : ''}
    </Badge>
  );
}

/* -------------------------------------------------------------------------- */
/* Confidence                                                                 */
/* -------------------------------------------------------------------------- */
export function ConfidenceMeter({
  value,
  showValue = true,
}: {
  value: number;
  showValue?: boolean;
}) {
  const band = confidenceBand(value);
  const pct = Math.round(value * 100);
  return (
    <span
      className={cn('confidence', `confidence--${band}`)}
      title={`Detection confidence: ${pct}% (${band})`}
    >
      <span className="meter" aria-hidden>
        <span className="meter__fill" style={{ width: `${pct}%` }} />
      </span>
      {showValue && <span>{pct}%</span>}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const band = confidenceBand(value);
  return (
    <Badge tone={CONFIDENCE_TONE[band]} title={`Detection confidence (${band})`}>
      {formatPercent(value)} conf.
    </Badge>
  );
}

/* -------------------------------------------------------------------------- */
/* Demo markers (mandatory for regulatory content)                           */
/* -------------------------------------------------------------------------- */
export function DemoBadge({ label = 'DEMO' }: { label?: string }) {
  return (
    <span className="demo-flag" title="DEMO DATA — NOT LEGAL ADVICE">
      <Icon name="alert" size={11} />
      {label}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="tag">{children}</span>;
}
