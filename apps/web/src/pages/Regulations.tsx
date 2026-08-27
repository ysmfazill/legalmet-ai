import { useState } from 'react';

import type { Tone } from '@legalmet/config';
import type { Rule } from '@legalmet/types';

import { Badge, DemoBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { RuleCard } from '../components/RuleCard';
import { RuleVersionTimeline } from '../components/RuleVersionTimeline';
import { Tabs } from '../components/Tabs';
import type { TabDef } from '../components/Tabs';
import { AsyncView } from '../components/states';
import { useAsync } from '../data/useAsync';
import { humanizeEnum } from '../lib/format';
import { mockApi } from '../mock/adapter';
import type { RuleRef } from '../mock/types';

type Tab = 'overview' | 'rules' | 'versions' | 'sources';

const TABS: TabDef<Tab>[] = [
  { id: 'overview', label: 'Regulation' },
  { id: 'rules', label: 'Rules' },
  { id: 'versions', label: 'Versions' },
  { id: 'sources', label: 'Sources' },
];

const RULE_STATUS_TONE: Record<string, Tone> = { ACTIVE: 'positive', DRAFT: 'info' };

export function RegulationsPage() {
  const query = useAsync(() => mockApi.getRegulation(), []);
  const [tab, setTab] = useState<Tab>('overview');

  return (
    <div className="page">
      <PageHeader
        eyebrow="Version-aware rule engine"
        title="Regulatory Intelligence"
        lead="The regulatory knowledge the rule engine resolves findings against — every requirement pinned to a specific, dated rule version."
        actions={<DemoBadge label="DEMO REGULATION" />}
      />

      <div className="demo-note demo-note--block">
        <Icon name="alert" size={15} />
        <span>
          <strong>DEMO DATA — NOT LEGAL ADVICE.</strong> Rule codes, versions and sources below are
          fictional placeholders to demonstrate version-aware validation. They are{' '}
          <strong>not official Legal Metrology citations</strong>.
        </span>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <AsyncView query={query} loadingLabel="Loading regulatory intelligence…">
        {({ regulation, versions, rules }) => {
          const versionsById = new Map(versions.map((v) => [v.id, v]));
          const activeVersion = versions.find((v) => v.status === 'ACTIVE');

          if (tab === 'overview') {
            return (
              <Card>
                <CardHead
                  eyebrow="Regulation"
                  title={regulation.title}
                  subtitle={`${regulation.code} · ${regulation.jurisdiction}`}
                  actions={<DemoBadge />}
                />
                <CardBody>
                  <dl className="kv">
                    <dt>Code</dt>
                    <dd>{regulation.code}</dd>
                    <dt>Jurisdiction</dt>
                    <dd>{regulation.jurisdiction}</dd>
                    <dt>Authority</dt>
                    <dd>{regulation.authority}</dd>
                    <dt>Active version</dt>
                    <dd>{activeVersion ? activeVersion.versionLabel : '—'}</dd>
                    <dt>Rules in force</dt>
                    <dd>{rules.filter((r) => r.status === 'ACTIVE').length}</dd>
                  </dl>
                  <p style={{ marginTop: 'var(--space-4)', color: 'var(--text-muted)', lineHeight: 'var(--lh-normal)' }}>
                    {regulation.description}
                  </p>
                </CardBody>
              </Card>
            );
          }

          if (tab === 'rules') {
            return (
              <div className="stack">
                {rules.map((rule) => {
                  const v = versionsById.get(rule.regulationVersionId);
                  const ref: RuleRef = {
                    code: rule.ruleCode,
                    title: rule.title,
                    requirement: rule.requirementSummary,
                    versionLabel: v?.versionLabel ?? '—',
                    effectiveFrom: v?.effectiveFrom ?? '—',
                    source: 'DEMO dataset — not an official citation',
                  };
                  return (
                    <Card key={rule.id}>
                      <CardBody>
                        <RuleCard rule={ref} />
                        <RuleEngineFoot rule={rule} />
                      </CardBody>
                    </Card>
                  );
                })}
              </div>
            );
          }

          if (tab === 'versions') {
            return (
              <SectionCard
                eyebrow="Amendment lineage"
                title="Version timeline"
                subtitle="Findings resolve against the ACTIVE version; superseded versions are retained for audit."
              >
                <RuleVersionTimeline versions={versions} />
                <div className="detail-list" style={{ marginTop: 'var(--space-5)' }}>
                  {[...versions]
                    .sort((a, b) => (b.effectiveFrom ?? '').localeCompare(a.effectiveFrom ?? ''))
                    .map((v) => (
                      <div key={v.id} className="detail-list__row">
                        <span className="detail-list__key">
                          {v.versionLabel}
                          <span className="tag" style={{ marginLeft: 8 }}>
                            {humanizeEnum(v.status)}
                          </span>
                        </span>
                        <span className="detail-list__val">
                          {v.effectiveFrom ?? '—'} → {v.effectiveUntil ?? 'present'}
                        </span>
                      </div>
                    ))}
                </div>
              </SectionCard>
            );
          }

          // sources
          return (
            <SectionCard
              eyebrow="Provenance"
              title="Sources"
              subtitle="Where each version's requirements are (notionally) drawn from."
              actions={<DemoBadge />}
            >
              <div className="detail-list">
                <div className="detail-list__row">
                  <span className="detail-list__key">Official source URL</span>
                  <span className="detail-list__val">
                    {regulation.officialSourceUrl ?? 'None — placeholder dataset (DEMO)'}
                  </span>
                </div>
                {versions.map((v) => (
                  <div key={v.id} className="detail-list__row">
                    <span className="detail-list__key">{v.versionLabel}</span>
                    <span className="detail-list__val" style={{ fontFamily: 'var(--font-mono)' }}>
                      {v.sourceDocumentRef ?? '—'}
                    </span>
                  </div>
                ))}
              </div>
              <p style={{ marginTop: 'var(--space-4)', fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
                Source references (DEMO-DOC-*) are illustrative identifiers only and do not correspond to
                any real legal document.
              </p>
            </SectionCard>
          );
        }}
      </AsyncView>
    </div>
  );
}

function RuleEngineFoot({ rule }: { rule: Rule }) {
  return (
    <div className="row row--wrap" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
      <Badge tone={RULE_STATUS_TONE[rule.status] ?? 'neutral'}>{humanizeEnum(rule.status)}</Badge>
      <span className="tag" title="Deterministic validator in the rule-engine registry">
        {rule.validationLogicRef}
      </span>
      {rule.evidenceRequirement && (
        <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          Evidence: {rule.evidenceRequirement}
        </span>
      )}
    </div>
  );
}
