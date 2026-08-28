/**
 * Regulatory Intelligence page (Prompt 5).
 *
 * Renders the real Source → Document → Version → Requirement hierarchy from
 * the API, with the honesty markers the phase demands:
 *
 *   - the one seeded source is UNVERIFIED research-grade material — the UI
 *     shows that state everywhere a source is named, and never dresses it up
 *     as official law;
 *   - version windows and the amendment lineage make "which text was in force
 *     when" inspectable, including the explicit NO_APPLICABLE_VERSION case;
 *   - requirement cards carry their full provenance (authority, document
 *     identifier, version, source reference);
 *   - DEMO regulatory rows (the Prompt 1 dataset) remain clearly labelled.
 *
 * Nothing here evaluates compliance. The strongest statement this page makes
 * about any requirement is that it is a definition with provenance.
 */
import { useMemo, useState } from 'react';

import {
  DOCUMENT_TYPE_META,
  REQUIREMENT_TYPE_META,
  SOURCE_TYPE_META,
} from '@legalmet/config';
import type { Tone } from '@legalmet/config';
import type {
  Regulation,
  RegulationVersion,
  RegulatoryRequirement,
  RegulatorySource,
} from '@legalmet/types';

import { api } from '../api/client';
import { Badge, DemoBadge, VerificationBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { RuleVersionTimeline } from '../components/RuleVersionTimeline';
import { Tabs } from '../components/Tabs';
import type { TabDef } from '../components/Tabs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDate, humanizeEnum } from '../lib/format';

type Tab = 'documents' | 'requirements' | 'versions' | 'sources';

const TABS: TabDef<Tab>[] = [
  { id: 'documents', label: 'Documents' },
  { id: 'requirements', label: 'Requirements' },
  { id: 'versions', label: 'Versions' },
  { id: 'sources', label: 'Sources' },
];

const RULE_STATUS_TONE: Record<string, Tone> = { ACTIVE: 'positive', DRAFT: 'info' };

/** Data the page needs in one shot: real hierarchy + demo rows for contrast. */
interface RegulatoryBundle {
  sources: RegulatorySource[];
  realDocuments: Regulation[];
  demoDocuments: Regulation[];
  requirements: RegulatoryRequirement[];
  totalRequirements: number;
}

function loadBundle(): Promise<RegulatoryBundle> {
  return Promise.all([
    api.listRegulatorySources(),
    api.listRegulatoryDocuments({ isDemo: false }),
    api.listRegulatoryDocuments({ isDemo: true }),
    api.listRegulatoryRequirements({ isDemo: false, pageSize: 100 }),
  ]).then(([sources, realDocuments, demoDocuments, requirements]) => ({
    sources,
    realDocuments,
    demoDocuments,
    requirements: requirements.items,
    totalRequirements: requirements.total,
  }));
}

export function RegulationsPage() {
  const query = useAsync(loadBundle, []);
  const [tab, setTab] = useState<Tab>('documents');

  // Derived from the loaded bundle; safe to compute unconditionally (empty
  // map while loading). Kept outside AsyncView's render callback so hook
  // ordering is stable.
  const versionsById = useMemo(() => {
    const map = new Map<string, RegulationVersion>();
    for (const doc of query.data?.realDocuments ?? []) {
      for (const version of doc.versions ?? []) map.set(version.id, version);
    }
    return map;
  }, [query.data]);
  const versionList = useMemo(
    () =>
      [...versionsById.values()].sort((a, b) =>
        (a.effectiveFrom ?? '').localeCompare(b.effectiveFrom ?? ''),
      ),
    [versionsById],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Version-aware regulatory knowledge"
        title="Regulatory Intelligence"
        lead="The Source → Document → Version → Requirement hierarchy the compliance engine will resolve against — every requirement pinned to a dated version of a sourced document."
      />

      <div className="demo-note demo-note--block">
        <Icon name="alert" size={15} />
        <span>
          <strong>RESEARCH DATA — NOT AN OFFICIAL LEGAL SOURCE.</strong> The seeded material
          (Legal Metrology (Packaged Commodities) Rules, 2011) is UNVERIFIED research-grade
          content. Regulatory intelligence is <strong>not itself a legal determination</strong>.
        </span>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <AsyncView query={query} loadingLabel="Loading regulatory intelligence…">
        {(bundle) => {
          if (bundle.realDocuments.length === 0) {
            return (
              <EmptyState
                icon="regulations"
                title="No sourced regulatory documents"
                message="The regulatory layer has no real (non-DEMO) documents yet. Run the API with the regulatory seed enabled, or import documents via the API."
              />
            );
          }

          if (tab === 'sources') {
            return <SourcesTab sources={bundle.sources} />;
          }
          if (tab === 'versions') {
            return <VersionsTab versions={versionList} documents={bundle.realDocuments} />;
          }
          if (tab === 'requirements') {
            return (
              <RequirementsTab
                requirements={bundle.requirements}
                versionsById={versionsById}
                total={bundle.totalRequirements}
              />
            );
          }
          return <DocumentsTab bundle={bundle} />;
        }}
      </AsyncView>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tab: documents                                                              */
/* -------------------------------------------------------------------------- */

function DocumentsTab({ bundle }: { bundle: RegulatoryBundle }) {
  return (
    <div className="stack">
      {bundle.realDocuments.map((doc) => (
        <Card key={doc.id}>
          <CardHead
            eyebrow={DOCUMENT_TYPE_META[doc.documentType]?.label ?? humanizeEnum(doc.documentType)}
            title={doc.title}
            subtitle={`${doc.code} · ${doc.jurisdiction}`}
            actions={
              bundle.sources.find((s) => s.id === doc.sourceId) ? (
                <VerificationBadge
                  status={
                    bundle.sources.find((s) => s.id === doc.sourceId)!.verificationStatus
                  }
                />
              ) : undefined
            }
          />
          <CardBody>
            <dl className="kv">
              <dt>Authority</dt>
              <dd>{doc.authority}</dd>
              <dt>Document identifier</dt>
              <dd style={{ fontFamily: 'var(--font-mono)' }}>
                {doc.documentIdentifier ?? '—'}
              </dd>
              <dt>Publication date</dt>
              <dd>{doc.publicationDate ? formatDate(doc.publicationDate) : '—'}</dd>
              <dt>Versions</dt>
              <dd>{doc.versions?.length ?? '—'}</dd>
            </dl>
            {doc.description && (
              <p
                style={{
                  marginTop: 'var(--space-4)',
                  color: 'var(--text-muted)',
                  lineHeight: 'var(--lh-normal)',
                }}
              >
                {doc.description}
              </p>
            )}
            {doc.officialSourceUrl && (
              <p style={{ marginTop: 'var(--space-3)', fontSize: 'var(--fs-sm)' }}>
                Official source:{' '}
                <a href={doc.officialSourceUrl} target="_blank" rel="noreferrer">
                  {doc.officialSourceUrl}
                </a>
              </p>
            )}
          </CardBody>
        </Card>
      ))}

      {bundle.demoDocuments.length > 0 && (
        <SectionCard
          eyebrow="Prompt 1 dataset"
          title="DEMO documents"
          subtitle="The fictional demonstration dataset, kept strictly separate from sourced regulatory material."
          actions={<DemoBadge label="DEMO DATA" />}
        >
          <div className="detail-list">
            {bundle.demoDocuments.map((d) => (
              <div key={d.id} className="detail-list__row">
                <span className="detail-list__key">
                  {d.code} <DemoBadge />
                </span>
                <span className="detail-list__val">{d.title}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tab: requirements                                                           */
/* -------------------------------------------------------------------------- */

function RequirementsTab({
  requirements,
  versionsById,
  total,
}: {
  requirements: RegulatoryRequirement[];
  versionsById: Map<string, RegulationVersion>;
  total: number;
}) {
  if (requirements.length === 0) {
    return (
      <EmptyState
        icon="regulations"
        title="No sourced requirements"
        message="No real (non-DEMO) requirement definitions exist yet."
      />
    );
  }
  return (
    <div className="stack">
      <p style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
        Showing {requirements.length} of {total} sourced requirement definitions.
      </p>
      {requirements.map((req) => {
        const version = versionsById.get(req.versionId);
        return (
          <Card key={req.id}>
            <CardBody>
              <div className="row row--between row--wrap" style={{ gap: 'var(--space-2)' }}>
                <div className="row" style={{ gap: 'var(--space-2)' }}>
                  <span className="tag" title="Requirement reference">
                    {req.ruleCode}
                  </span>
                  <strong>{req.title}</strong>
                </div>
                <Badge tone={RULE_STATUS_TONE[req.status] ?? 'neutral'} dot>
                  {humanizeEnum(req.status)}
                </Badge>
              </div>
              <p
                style={{
                  marginTop: 'var(--space-3)',
                  color: 'var(--text-muted)',
                  lineHeight: 'var(--lh-normal)',
                }}
              >
                {req.description}
              </p>
              <dl className="kv" style={{ marginTop: 'var(--space-3)' }}>
                <dt>Requirement type</dt>
                <dd>{REQUIREMENT_TYPE_META[req.requirementType]?.label ?? req.requirementType}</dd>
                <dt>Version in force</dt>
                <dd>{version?.versionLabel ?? '—'}</dd>
                <dt>Effective window</dt>
                <dd>
                  {version
                    ? `${version.effectiveFrom ?? '—'} → ${version.effectiveUntil ?? 'present'}`
                    : '—'}
                </dd>
                <dt>Source reference</dt>
                <dd style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                  {req.sourceReference ?? '—'}
                </dd>
                {req.fieldKey && (
                  <>
                    <dt>Mapped field</dt>
                    <dd>{req.fieldKey}</dd>
                  </>
                )}
              </dl>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tab: versions                                                               */
/* -------------------------------------------------------------------------- */

function VersionsTab({
  versions,
  documents,
}: {
  versions: RegulationVersion[];
  documents: Regulation[];
}) {
  if (versions.length === 0) {
    return (
      <EmptyState
        icon="regulations"
        title="No versions"
        message="No regulatory version windows exist yet."
      />
    );
  }
  const docById = new Map(documents.map((d) => [d.id, d]));
  return (
    <SectionCard
      eyebrow="Amendment lineage"
      title="Version timeline"
      subtitle="Each version's requirement set is frozen at its effective date; superseded versions are retained for audit — never overwritten."
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
                {docById.get(v.regulationId)?.code ?? v.regulationId} ·{' '}
                {v.effectiveFrom ?? '—'} → {v.effectiveUntil ?? 'present'}
              </span>
            </div>
          ))}
      </div>
      <p
        style={{
          marginTop: 'var(--space-4)',
          fontSize: 'var(--fs-sm)',
          color: 'var(--text-faint)',
        }}
      >
        Version selection is deterministic: the version whose [effectiveFrom, effectiveUntil)
        window contains the requested date is used. If no version is in force, the result is an
        explicit NO_APPLICABLE_VERSION — the resolver never silently falls back to the newest
        version.
      </p>
    </SectionCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Tab: sources                                                                */
/* -------------------------------------------------------------------------- */

function SourcesTab({ sources }: { sources: RegulatorySource[] }) {
  if (sources.length === 0) {
    return (
      <EmptyState
        icon="regulations"
        title="No sources registered"
        message="The provenance hierarchy is empty at the source level."
      />
    );
  }
  return (
    <div className="stack">
      {sources.map((source) => (
        <Card key={source.id}>
          <CardHead
            eyebrow={SOURCE_TYPE_META[source.sourceType]?.label ?? source.sourceType}
            title={source.name}
            subtitle={source.authority}
            actions={<VerificationBadge status={source.verificationStatus} />}
          />
          <CardBody>
            <dl className="kv">
              <dt>Jurisdiction</dt>
              <dd>{source.jurisdiction}</dd>
              <dt>Canonical URL</dt>
              <dd>
                {source.canonicalUrl ? (
                  <a href={source.canonicalUrl} target="_blank" rel="noreferrer">
                    {source.canonicalUrl}
                  </a>
                ) : (
                  '—'
                )}
              </dd>
            </dl>
            {source.verificationNote && (
              <div
                className={
                  source.verificationStatus === 'UNVERIFIED' ? 'demo-note demo-note--block' : ''
                }
                style={{ marginTop: 'var(--space-4)' }}
              >
                <strong>Verification note:</strong> {source.verificationNote}
              </div>
            )}
            <p
              style={{
                marginTop: 'var(--space-3)',
                fontSize: 'var(--fs-sm)',
                color: 'var(--text-faint)',
              }}
            >
              Moving a source to VERIFIED is an audited administrator action and requires a
              verification note recording how the content was checked against the official
              publication. Unverified data is ineligible for production compliance evaluation.
            </p>
          </CardBody>
        </Card>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* helpers                                                                     */
/* -------------------------------------------------------------------------- */
