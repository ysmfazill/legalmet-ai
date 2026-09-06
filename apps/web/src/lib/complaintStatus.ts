import type { CitizenReportStatus } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

/**
 * Centralised complaint status definitions (UI-03).
 *
 * The status VALUES live in @legalmet/types (mirroring the backend state
 * machine); this module owns their presentation: labels, tones, hints, the
 * department track order, and the citizen-visible filter groups. No page may
 * invent its own status strings or progress logic.
 */

export interface StatusMeta {
  label: string;
  tone: Tone;
  hint: string;
}

export const COMPLAINT_STATUS_META: Record<CitizenReportStatus, StatusMeta> = {
  SUBMITTED: {
    label: 'Submitted',
    tone: 'info',
    hint: 'Received — awaiting official review',
  },
  UNDER_REVIEW: {
    label: 'Under review',
    tone: 'warning',
    hint: 'A department officer is reviewing the complaint',
  },
  REJECTED: {
    label: 'Rejected',
    tone: 'neutral',
    hint: 'The department did not accept this complaint',
  },
  REQUEST_INFORMATION: {
    label: 'Information requested',
    tone: 'warning',
    hint: 'The department has asked the citizen for more information',
  },
  ACCEPTED: {
    label: 'Accepted',
    tone: 'info',
    hint: 'Accepted for further review',
  },
  ASSIGNED: {
    label: 'Assigned',
    tone: 'info',
    hint: 'An inspector has been assigned',
  },
  INSPECTION_SCHEDULED: {
    label: 'Inspection scheduled',
    tone: 'info',
    hint: 'A field inspection has been created from this complaint',
  },
  INSPECTION_COMPLETED: {
    label: 'Inspection completed',
    tone: 'info',
    hint: 'The field inspection has been completed',
  },
  ACTION_TAKEN: {
    label: 'Action taken',
    tone: 'positive',
    hint: 'Enforcement action has been recorded',
  },
  CLOSED: {
    label: 'Closed',
    tone: 'neutral',
    hint: 'The complaint is closed',
  },
};

/** Department lifecycle track (excludes REJECTED — it is a terminal branch). */
export const COMPLAINT_TRACK_ORDER: CitizenReportStatus[] = [
  'SUBMITTED',
  'UNDER_REVIEW',
  'ACCEPTED',
  'ASSIGNED',
  'INSPECTION_SCHEDULED',
  'INSPECTION_COMPLETED',
  'ACTION_TAKEN',
  'CLOSED',
];

export const COMPLAINT_TERMINAL_STATUSES: CitizenReportStatus[] = ['REJECTED', 'CLOSED'];

/** My Reports filter tabs (spec: All / Submitted / Under Review / Accepted / Completed / Closed). */
export type CitizenFilterId = 'ALL' | 'SUBMITTED' | 'UNDER_REVIEW' | 'ACCEPTED' | 'COMPLETED' | 'CLOSED';

const COMPLETED_GROUP: CitizenReportStatus[] = [
  'INSPECTION_SCHEDULED',
  'INSPECTION_COMPLETED',
  'ACTION_TAKEN',
];

export function matchesCitizenFilter(
  status: CitizenReportStatus,
  filter: CitizenFilterId,
): boolean {
  if (filter === 'ALL') return true;
  if (filter === 'COMPLETED') return COMPLETED_GROUP.includes(status);
  return status === filter;
}

/** Human labels for recorded timeline events (real rows only — never derived). */
const EVENT_LABELS: Record<string, string> = {
  SUBMITTED: 'Complaint submitted',
  REVIEW_STARTED: 'Review started',
  ACCEPTED: 'Complaint accepted',
  REJECTED: 'Complaint rejected',
  INFORMATION_REQUESTED: 'Information requested',
  INFORMATION_PROVIDED: 'Information provided',
  ASSIGNED: 'Inspector assigned',
  INSPECTION_CREATED: 'Inspection created',
  INSPECTION_COMPLETED: 'Inspection completed',
  ACTION_TAKEN: 'Action taken',
  CLOSED: 'Complaint closed',
};

export function complaintEventLabel(event: string): string {
  return EVENT_LABELS[event] ?? event;
}

/** Risk levels — SYSTEM SCREENING and OFFICIAL decision are distinct sources. */
export const COMPLAINT_RISK_META: Record<string, { label: string; tone: Tone }> = {
  HIGH: { label: 'High', tone: 'critical' },
  MEDIUM: { label: 'Medium', tone: 'warning' },
  LOW: { label: 'Low', tone: 'neutral' },
};
