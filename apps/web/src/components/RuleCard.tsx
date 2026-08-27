import type { Tone } from '@legalmet/config';

import type { RuleRef, ValidationResult } from '../mock/types';
import { Badge, DemoBadge } from './Badge';
import { Icon } from './Icon';

const RESULT_TONE: Record<ValidationResult, Tone> = {
  PASS: 'positive',
  FAIL: 'critical',
  INCONCLUSIVE: 'warning',
};

/**
 * The applicable requirement panel (DEMO rule). Shows the rule, its version,
 * and the deterministic Expected / Detected / Result validation — never a
 * legal conclusion, and always marked DEMO DATA — NOT LEGAL ADVICE.
 */
export function RuleCard({
  rule,
  expected,
  detected,
  result,
}: {
  rule: RuleRef;
  expected?: string;
  detected?: string;
  result?: ValidationResult;
}) {
  return (
    <div className="stack stack--sm">
      <div className="row row--between row--wrap">
        <div className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="tag">{rule.code}</span>
          <strong>{rule.title}</strong>
        </div>
        <DemoBadge />
      </div>

      <p style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-md)', lineHeight: 'var(--lh-normal)' }}>
        {rule.requirement}
      </p>

      <div className="row row--wrap" style={{ gap: 'var(--space-2)', fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
        <span className="row" style={{ gap: 4 }}>
          <Icon name="layers" size={13} /> {rule.versionLabel}
        </span>
        <span className="row" style={{ gap: 4 }}>
          <Icon name="clock" size={13} /> Effective {rule.effectiveFrom}
        </span>
      </div>

      {(expected || detected || result) && (
        <div className="rule-validation">
          <div className="rule-validation__cell">
            <div className="rule-validation__cell-label">Expected</div>
            {expected ?? '—'}
          </div>
          <div className="rule-validation__cell">
            <div className="rule-validation__cell-label">Detected</div>
            {detected ?? '—'}
          </div>
          <div className="rule-validation__cell">
            <div className="rule-validation__cell-label">Result</div>
            {result ? <Badge tone={RESULT_TONE[result]}>{result}</Badge> : '—'}
          </div>
        </div>
      )}

      <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>Source: {rule.source}</p>
    </div>
  );
}
