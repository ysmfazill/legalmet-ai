import { useState } from 'react';
import type { ReactNode } from 'react';

import { FIELD_TYPE_LABELS, REVIEW_ACTION_META } from '@legalmet/config';
import type { ReviewActionType } from '@legalmet/types';

import { mockApi } from '../mock/adapter';
import type { FindingView } from '../mock/types';
import { ConfidenceMeter, DemoBadge, RiskBadge, StatusBadge } from './Badge';
import { ActionBar } from './ActionBar';
import type { ActionOption } from './ActionBar';
import { Drawer } from './Drawer';
import { EvidenceChain } from './EvidenceChain';
import { Icon } from './Icon';
import { RuleCard } from './RuleCard';

const REVIEW_OPTIONS: ActionOption[] = [
  { id: 'ACCEPT', label: REVIEW_ACTION_META.ACCEPT.label, icon: 'check' },
  { id: 'REJECT', label: REVIEW_ACTION_META.REJECT.label, icon: 'close' },
  { id: 'CORRECT', label: REVIEW_ACTION_META.CORRECT.label, icon: 'edit' },
  { id: 'REQUEST_RESCAN', label: REVIEW_ACTION_META.REQUEST_RESCAN.label, icon: 'camera' },
  { id: 'ESCALATE', label: REVIEW_ACTION_META.ESCALATE.label, icon: 'alert' },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="stack stack--sm">
      <div className="eyebrow">{title}</div>
      {children}
    </section>
  );
}

/**
 * THE WHY / EVIDENCE EXPERIENCE — the core differentiator.
 *
 * Walks a judge from "AI detected something" → "here is the evidence" → "here
 * is the applicable requirement" → "here is why it was flagged" → "the
 * inspector makes the final decision". The system never concludes; it assists.
 */
export function EvidenceDrawer({
  finding,
  onClose,
  onReviewed,
}: {
  finding: FindingView;
  onClose: () => void;
  onReviewed?: (findingId: string, action: ReviewActionType) => void;
}) {
  const [action, setAction] = useState<ReviewActionType | null>(null);
  const [note, setNote] = useState('');
  const [phase, setPhase] = useState<'idle' | 'saving' | 'done'>('idle');

  async function submit() {
    if (!action) return;
    setPhase('saving');
    await mockApi.recordReview(finding.id, action, note || undefined);
    setPhase('done');
    onReviewed?.(finding.id, action);
  }

  const footer =
    phase === 'done' ? (
      <button type="button" className="btn btn--primary" onClick={onClose}>
        Close
      </button>
    ) : (
      <>
        <button type="button" className="btn btn--subtle" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!action || phase === 'saving'}
          onClick={submit}
        >
          {phase === 'saving' ? 'Recording…' : 'Record decision'}
        </button>
      </>
    );

  return (
    <Drawer
      wide
      title={finding.title}
      subtitle="Evidence & decision"
      onClose={onClose}
      footer={footer}
    >
      <div className="stack">
        <div className="row row--wrap">
          <StatusBadge status={finding.status} />
          <RiskBadge risk={finding.risk} />
          <ConfidenceMeter value={finding.confidence} />
        </div>

        <Section title="Why this finding was created">
          <p style={{ color: 'var(--text-muted)', lineHeight: 'var(--lh-normal)' }}>{finding.rationale}</p>
        </Section>

        <Section title="Detected information">
          <div className="detail-list">
            <div className="detail-list__row">
              <span className="detail-list__key">Field</span>
              <span className="detail-list__val">
                {finding.fieldType ? FIELD_TYPE_LABELS[finding.fieldType] : '—'}
              </span>
            </div>
            <div className="detail-list__row">
              <span className="detail-list__key">Detected value</span>
              <span className="detail-list__val" style={{ fontFamily: 'var(--font-mono)' }}>
                {finding.detectedValue ?? 'Not detected'}
              </span>
            </div>
            <div className="detail-list__row">
              <span className="detail-list__key">Evidence region</span>
              <span className="detail-list__val">
                {finding.regionId ? 'Highlighted on label' : 'No region detected'}
              </span>
            </div>
            <div className="detail-list__row">
              <span className="detail-list__key">Detection confidence</span>
              <span className="detail-list__val">
                <ConfidenceMeter value={finding.confidence} />
              </span>
            </div>
          </div>
        </Section>

        <Section title="Applicable requirement">
          {finding.rule ? (
            <RuleCard
              rule={finding.rule}
              expected={finding.expected}
              detected={finding.detected}
              result={finding.validationResult}
            />
          ) : (
            <div className="demo-note demo-note--block">
              <Icon name="info" size={15} />
              No applicable rule resolved for this field in the demo product context.
            </div>
          )}
        </Section>

        <Section title="Evidence chain">
          <EvidenceChain nodes={finding.chain} />
        </Section>

        <Section title="Inspector review">
          <div className="demo-note demo-note--block">
            <Icon name="shield" size={15} />
            The system does not make the legal decision. It surfaces evidence and a suggested status
            for you to <strong>&nbsp;accept, reject, correct, escalate or request a rescan</strong>.
          </div>

          {phase === 'done' ? (
            <div className="demo-note" style={{ color: 'var(--tone-positive)', background: 'var(--tone-positive-soft)', borderColor: 'transparent' }}>
              <Icon name="check" size={15} />
              Decision recorded (demo): <strong>&nbsp;{action && REVIEW_ACTION_META[action].label}</strong>. The
              backend would persist this and write an audit event.
            </div>
          ) : (
            <>
              <ActionBar
                options={REVIEW_OPTIONS}
                selected={action}
                onSelect={(id) => setAction(id as ReviewActionType)}
                ariaLabel="Inspector decision"
              />
              <label className="field">
                <span className="field__label">Reviewer note (optional)</span>
                <textarea
                  className="textarea"
                  value={note}
                  placeholder="Add context for the audit trail…"
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
            </>
          )}
        </Section>

        <div className="row" style={{ gap: 6 }}>
          <DemoBadge />
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
            Regulatory content shown here is placeholder data for demonstration only.
          </span>
        </div>
      </div>
    </Drawer>
  );
}
