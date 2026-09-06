/**
 * Report badges + small presentational helpers (UI-08).
 *
 * Shared by the Report Center list and the detail page: status, result and
 * evidence-status chips resolved through the config META maps so labels and
 * tones come from one place.
 */
import { REPORT_STATUS_META, REPORT_RESULT_META } from '@legalmet/config';
import type { Tone } from '@legalmet/config';

import { Badge } from '../components/Badge';
import { humanizeEnum } from '../lib/format';

export function ReportStatusChip({ status }: { status: string }) {
  const meta = REPORT_STATUS_META[status as keyof typeof REPORT_STATUS_META];
  return (
    <Badge tone={meta?.tone ?? 'neutral'} dot>
      {meta?.label ?? humanizeEnum(status)}
    </Badge>
  );
}

export function ReportResultChip({ result }: { result: string }) {
  const meta = REPORT_RESULT_META[result];
  return (
    <Badge tone={meta?.tone ?? 'neutral'}>{meta?.label ?? humanizeEnum(result)}</Badge>
  );
}

const EVIDENCE_STATUS_TONE: Record<string, Tone> = {
  VERIFIED: 'positive',
  AVAILABLE: 'positive',
  CONFIRMED: 'positive',
  REQUIRES_VERIFICATION: 'warning',
  PENDING_REVIEW: 'warning',
  ESCALATED: 'warning',
  MISSING: 'critical',
  REJECTED: 'critical',
  ABSENT: 'warning',
};

export function EvidenceStatusChip({ status }: { status: string }) {
  return (
    <Badge tone={EVIDENCE_STATUS_TONE[status] ?? 'neutral'} outline>
      {humanizeEnum(status)}
    </Badge>
  );
}

const SOURCE_META: Record<string, { label: string; tone: Tone }> = {
  SOURCE: { label: 'Source (citizen)', tone: 'info' },
  OFFICIAL: { label: 'Official (inspection)', tone: 'positive' },
};

/** §4: source evidence and official evidence are labelled distinctly. */
export function EvidenceSourceChip({ source }: { source: string }) {
  const meta = SOURCE_META[source] ?? { label: humanizeEnum(source), tone: 'neutral' };
  return (
    <Badge tone={meta.tone} outline>
      {meta.label}
    </Badge>
  );
}
