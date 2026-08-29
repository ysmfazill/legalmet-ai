/**
 * Engine-finding explanation drawer (Prompt 6).
 *
 * Opens when an inspector clicks a compliance-engine finding. Shows the full
 * deterministic trace for that single finding:
 *
 *   STATUS → DETECTED vs EXPECTED → THE SEVEN-QUESTION EXPLANATION →
 *   PER-RULE OUTCOMES (pass/fail/indeterminate + reason) → FROZEN PROVENANCE
 *   (requirement → version → document → source)
 *
 * Boundary statement: this drawer renders a SYSTEM finding. It never offers
 * an approve/reject action — recording the inspector's final enforcement
 * decision is a later phase, and the inspector remains responsible for it.
 */
import {
  APPLICABILITY_OUTCOME_META,
  ENGINE_FINDING_STATUS_META,
} from '@legalmet/config';

import type { EngineFinding } from '@legalmet/types';

import { ApplicabilityBadge, EngineFindingBadge } from '../components/Badge';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-list__row">
      <span className="detail-list__key">{label}</span>
      <span className="detail-list__val">{children}</span>
    </div>
  );
}

function ruleTone(passed: boolean | null) {
  if (passed === true) return 'var(--tone-positive)';
  if (passed === false) return 'var(--tone-critical)';
  return 'var(--tone-warning)';
}

function ruleWord(passed: boolean | null) {
  if (passed === true) return 'PASS';
  if (passed === false) return 'FAIL';
  return 'INDETERMINATE';
}

export function FindingExplanationDrawer({
  finding,
  onClose,
}: {
  finding: EngineFinding;
  onClose: () => void;
}) {
  const provenance = finding.provenance ?? {};
  const rules = finding.detail?.rules ?? [];
  const requirementCode = provenance.requirementCode ?? 'Requirement';

  return (
    <Drawer
      wide
      title={requirementCode}
      subtitle="System finding — inspector decision pending"
      onClose={onClose}
    >
      <div className="stack">
        <div className="row row--wrap">
          <EngineFindingBadge status={finding.status} />
          <ApplicabilityBadge outcome={finding.applicability} />
          {provenance.versionLabel && <span className="tag">{provenance.versionLabel}</span>}
        </div>

        <p className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Icon name="info" size={15} />
          <span>
            <strong>System finding — not an enforcement determination.</strong> This conclusion was
            produced by the deterministic compliance engine from the detected evidence and the
            regulatory version in force. The inspector remains responsible for the final decision.
          </span>
        </p>

        <section className="stack stack--sm">
          <div className="eyebrow">Detected vs expected</div>
          <div className="detail-list">
            <Row label="Detected value">
              {finding.detectedValue ? (
                <span style={{ fontFamily: 'var(--font-mono)' }}>{finding.detectedValue}</span>
              ) : (
                <span style={{ color: 'var(--text-muted)' }}>
                  Nothing detected — this is not evidence the declaration is absent
                </span>
              )}
            </Row>
            <Row label="Expected">
              {finding.expectedValue ?? '—'}
            </Row>
            {finding.detail?.absence && (
              <Row label="Absence reason">
                <span className="tag">{finding.detail.absence}</span>{' '}
                <span style={{ color: 'var(--text-faint)', fontSize: 'var(--fs-sm)' }}>
                  (FIELD_NOT_FOUND — missing OCR, never a violation)
                </span>
              </Row>
            )}
            <Row label="Evaluated at">{formatDateTime(finding.createdAt)}</Row>
          </div>
        </section>

        <section className="stack stack--sm">
          <div className="eyebrow">Why this conclusion (deterministic explanation)</div>
          <p style={{ margin: 0, lineHeight: 1.6 }}>{finding.explanation}</p>
        </section>

        {rules.length > 0 && (
          <section className="stack stack--sm">
            <div className="eyebrow">Rule trace</div>
            <div className="stack stack--sm">
              {rules.map((rule) => (
                <div
                  key={rule.ruleCode}
                  className="detail-list"
                  style={{
                    paddingLeft: 'var(--space-3)',
                    borderLeft: `3px solid ${ruleTone(rule.passed)}`,
                  }}
                >
                  <Row label="Rule">
                    <span className="tag" style={{ marginRight: 8 }}>{rule.ruleType}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                      {rule.ruleCode}
                    </span>
                  </Row>
                  <Row label="Outcome">
                    <span style={{ color: ruleTone(rule.passed), fontWeight: 600 }}>
                      {ruleWord(rule.passed)}
                    </span>
                    {rule.errorCode && (
                      <span className="tag" style={{ marginLeft: 8 }}>{rule.errorCode}</span>
                    )}
                  </Row>
                  {rule.expected && <Row label="Expected">{rule.expected}</Row>}
                  <Row label="Reason">{rule.reason}</Row>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="stack stack--sm">
          <div className="eyebrow">Regulatory provenance (frozen at evaluation time)</div>
          <div className="detail-list">
            <Row label="Requirement">
              {provenance.requirementCode}
              {provenance.requirementTitle ? ` — ${provenance.requirementTitle}` : ''}
            </Row>
            {provenance.reference && (
              <Row label="Reference">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                  {provenance.reference}
                </span>
              </Row>
            )}
            <Row label="Version in force">
              {provenance.versionLabel ?? '—'}
              {provenance.effectiveFrom ? ` (from ${provenance.effectiveFrom.slice(0, 10)})` : ''}
            </Row>
            {provenance.documentTitle && <Row label="Document">{provenance.documentTitle}</Row>}
            <Row label="Source">
              {provenance.sourceName ?? '—'}
              {provenance.sourceVerificationStatus ? ` · ${provenance.sourceVerificationStatus}` : ''}
            </Row>
          </div>
        </section>

        <section className="stack stack--sm">
          <div className="eyebrow">Evidence</div>
          <div className="detail-list">
            <Row label="Extracted field">
              {finding.extractedFieldId ? (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                  {finding.extractedFieldId}
                </span>
              ) : (
                '— (no perceived field for this requirement)'
              )}
            </Row>
            <Row label="Evidence region">
              {finding.evidenceRegionId ? (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                  {finding.evidenceRegionId}
                </span>
              ) : (
                '—'
              )}
            </Row>
            <Row label="Evidence fields considered">
              {finding.detail?.evidenceCount ?? 0}
            </Row>
          </div>
        </section>

        <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
          {ENGINE_FINDING_STATUS_META[finding.status].description} Applicability:{' '}
          {APPLICABILITY_OUTCOME_META[finding.applicability].description}
        </p>
      </div>
    </Drawer>
  );
}
