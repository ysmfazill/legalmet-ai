import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { INSPECTION_STATUS_META } from '@legalmet/config';
import type { Tone } from '@legalmet/config';
import type { Inspection, PackageImage } from '@legalmet/types';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import {
  ImageProcessingBadge,
  ImageQualityGradeBadge,
  InspectionStatusBadge,
} from '../components/Badge';
import { BarList } from '../components/charts';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { DeclarationField } from '../components/DeclarationField';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { EvidenceViewer } from '../components/EvidenceViewer';
import { FindingCard } from '../components/FindingCard';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { QualityReadout } from '../intake/QualityReadout';
import { useObjectUrl } from '../intake/useObjectUrl';
import { formatBytes, formatDateTime, humanizeEnum } from '../lib/format';
import { toneColor, toneSoft } from '../lib/tone';
import { mockApi } from '../mock/adapter';
import { countsFrom, inspectorName } from '../mock/fixtures';
import type { FindingView, InspectionDetail } from '../mock/types';

const WORKED_DEMOS = [
  { id: 'ins-10482', label: 'INS-10482 · Namkeen' },
  { id: 'ins-10483', label: 'INS-10483 · Drinking Water' },
  { id: 'ins-10485', label: 'INS-10485 · Sunflower Oil' },
];

function qualityTone(score: number): Tone {
  return score >= 0.9 ? 'positive' : score >= 0.75 ? 'warning' : 'critical';
}

/**
 * One inspection id resolves to one of three things:
 *   - a fully-worked DEMO inspection (authored evidence + findings), or
 *   - a REAL intake inspection (uploaded image + provenance, NO analysis), or
 *   - nothing we can render.
 * Demo data is served by the mock adapter and always wins; real inspections are
 * fetched from the backend only when authenticated.
 */
type WorkspaceResult =
  | { kind: 'demo'; detail: InspectionDetail }
  | { kind: 'real'; inspection: Inspection }
  | { kind: 'none' };

export function WorkspacePage() {
  const { id = '' } = useParams();
  const { isLive } = useApp();

  const query = useAsync<WorkspaceResult>(async () => {
    const demo = await mockApi.getInspectionDetail(id);
    if (demo) return { kind: 'demo', detail: demo };
    if (isLive) {
      try {
        const inspection = await api.getInspection(id);
        return { kind: 'real', inspection };
      } catch {
        return { kind: 'none' };
      }
    }
    return { kind: 'none' };
  }, [id, isLive]);

  return (
    <div className="page">
      <AsyncView query={query} loadingLabel="Loading inspection workspace…">
        {(result) =>
          result.kind === 'demo' ? (
            <Workspace detail={result.detail} />
          ) : result.kind === 'real' ? (
            <RealInspectionWorkspace inspection={result.inspection} />
          ) : (
            <NoWorkspace />
          )
        }
      </AsyncView>
    </div>
  );
}

function NoWorkspace() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader eyebrow="Workspace" title="Inspection Workspace" />
      <Card>
        <CardBody>
          <EmptyState
            icon="image"
            title="No worked evidence for this inspection"
            message="Fully-linked evidence (regions, declarations, findings and rules) is authored for the demonstration inspections below."
            action={
              <div className="row row--wrap" style={{ gap: 'var(--space-2)', justifyContent: 'center' }}>
                {WORKED_DEMOS.map((d) => (
                  <button key={d.id} type="button" className="btn btn--subtle btn--sm" onClick={() => navigate(`/inspections/${d.id}`)}>
                    {d.label}
                  </button>
                ))}
              </div>
            }
          />
        </CardBody>
      </Card>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* REAL intake workspace — actual uploaded image + provenance.                */
/*                                                                            */
/* Deliberately shows NO OCR text, NO detected declarations, NO findings and  */
/* NO compliance verdict — none of that exists at intake time. The strongest  */
/* state it can surface is READY_FOR_ANALYSIS.                                */
/* -------------------------------------------------------------------------- */
function RealInspectionWorkspace({ inspection }: { inspection: Inspection }) {
  const images = inspection.packages?.flatMap((p) => p.images ?? []) ?? [];
  const statusMeta = INSPECTION_STATUS_META[inspection.status];
  const isReady = inspection.status === 'READY_FOR_ANALYSIS';

  return (
    <>
      <PageHeader
        eyebrow={inspection.referenceNo}
        title={inspection.product?.name ?? 'Packaged commodity'}
        lead={`${inspection.product?.category ?? '—'} · Real package intake`}
        actions={
          <>
            <InspectionStatusBadge status={inspection.status} />
            <Link to="/inspections/new" className="btn btn--subtle btn--sm">
              <Icon name="camera" size={15} />
              New intake
            </Link>
            <Link to="/inspections" className="btn btn--ghost btn--sm">
              <Icon name="chevronLeft" size={15} />
              All inspections
            </Link>
          </>
        }
      />

      <div className="demo-note demo-note--block">
        <Icon name={isReady ? 'check' : 'info'} size={15} />
        <span>
          {isReady ? (
            <>
              <strong>Ready for analysis.</strong>{' '}
              {statusMeta?.description ?? 'The package is queued. No analysis has run yet.'} This is a
              real uploaded package — <strong>no OCR, computer vision or compliance result exists yet</strong>.
            </>
          ) : (
            <>
              <strong>{statusMeta?.label ?? humanizeEnum(inspection.status)}.</strong> Images are
              validated and stored with a deterministic <strong>usability</strong> grade. No compliance
              analysis runs at intake — the strongest outcome here is Ready for analysis.
            </>
          )}
        </span>
      </div>

      {images.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="image"
              title="No images on this inspection yet"
              message="Upload or capture label images from the New inspection page to populate this workspace."
            />
          </CardBody>
        </Card>
      ) : (
        <div className="stack">
          {images.map((image) => (
            <RealImageBlock key={image.id} image={image} />
          ))}
        </div>
      )}
    </>
  );
}

/** A single real stored image: the actual bytes plus full provenance + usability. */
function RealImageBlock({ image }: { image: PackageImage }) {
  const view = useObjectUrl(image.processedStorageKey ?? image.storageKey);
  const resolution =
    image.width && image.height ? `${image.width} × ${image.height}` : 'Pending';
  const score =
    image.qualityScore != null ? `${Math.round(image.qualityScore * 100)}/100` : '—';
  const shortChecksum = image.checksum ? `${image.checksum.slice(0, 12)}…` : '—';

  return (
    <div className="split">
      <div className="real-image">
        {view.status === 'ready' ? (
          <img src={view.url} alt={image.originalFilename} />
        ) : view.status === 'loading' ? (
          <span className="spinner" aria-hidden />
        ) : (
          <span className="intake-card__thumb-fallback" title={view.message}>
            <Icon name="image" size={26} />
          </span>
        )}
      </div>

      <div className="stack">
        <SectionCard
          eyebrow="Provenance"
          title={image.originalFilename}
          subtitle="Real stored image — metadata and usability only. No OCR or compliance."
        >
          <div className="row row--wrap" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
            <span className="tag">{image.captureSource}</span>
            <span className="tag">{image.imageType}</span>
            <ImageProcessingBadge status={image.processingStatus} />
            {image.qualityGrade && <ImageQualityGradeBadge grade={image.qualityGrade} />}
          </div>
          <dl className="meta-grid">
            <div>
              <dt>Image ID</dt>
              <dd title={image.id}>{image.id.slice(0, 8)}…</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{image.captureSource}</dd>
            </div>
            <div>
              <dt>Resolution</dt>
              <dd>{resolution}</dd>
            </div>
            <div>
              <dt>File size</dt>
              <dd>{formatBytes(image.fileSize)}</dd>
            </div>
            <div>
              <dt>Usability score</dt>
              <dd>{score}</dd>
            </div>
            <div>
              <dt>Processing</dt>
              <dd>{humanizeEnum(image.processingStatus)}</dd>
            </div>
            <div>
              <dt>Uploaded</dt>
              <dd>{formatDateTime(image.createdAt)}</dd>
            </div>
            <div>
              <dt>Checksum (SHA-256)</dt>
              <dd title={image.checksum ?? undefined}>{shortChecksum}</dd>
            </div>
          </dl>
        </SectionCard>

        <Card>
          <CardHead
            eyebrow="Perception"
            title="Image usability"
            subtitle="Deterministic legibility signal — not compliance, not AI confidence"
          />
          <CardBody>
            <QualityReadout image={image} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Workspace({ detail }: { detail: InspectionDetail }) {
  const { inspection, imageRegions, declarations, findings, quality, qualityScore, complianceScore } = detail;
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [openFinding, setOpenFinding] = useState<FindingView | null>(null);
  const [reviewedIds, setReviewedIds] = useState<Set<string>>(new Set());

  const counts = countsFrom(findings);
  const breakdown: { label: string; value: number; tone: Tone }[] = [
    { label: 'Compliant', value: counts.compliant, tone: 'positive' },
    { label: 'Review required', value: counts.reviewRequired, tone: 'warning' },
    { label: 'Potential violation', value: counts.potentialViolation, tone: 'critical' },
    { label: 'Not applicable', value: counts.notApplicable, tone: 'neutral' },
  ];

  const openFindingCard = (f: FindingView) => {
    setOpenFinding(f);
    if (f.regionId) setSelectedRegionId(f.regionId);
  };

  return (
    <>
      <PageHeader
        eyebrow={inspection.referenceNo}
        title={inspection.product?.name ?? 'Packaged commodity'}
        lead={`${inspection.product?.category ?? '—'} · Inspector ${inspectorName(inspection.inspectorId)}`}
        actions={
          <>
            <InspectionStatusBadge status={inspection.status} />
            <Link to="/reports" className="btn btn--subtle btn--sm">
              <Icon name="reports" size={15} />
              Report
            </Link>
            <Link to="/inspections" className="btn btn--ghost btn--sm">
              <Icon name="chevronLeft" size={15} />
              All inspections
            </Link>
          </>
        }
      />

      <div className="split">
        {/* LEFT — the physical package, scanned */}
        <div className="stack">
          <EvidenceViewer
            packageLabel={inspection.product?.name ?? 'Package'}
            regions={imageRegions}
            declarations={declarations}
            selectedRegionId={selectedRegionId}
            onSelectRegion={(rid) => setSelectedRegionId((cur) => (cur === rid ? null : rid))}
          />
          <Card>
            <CardHead
              eyebrow="Perception"
              title="Image quality"
              subtitle="Why the system trusts (or doubts) this scan"
              actions={<span className="badge badge--square">{qualityScore}/100</span>}
            />
            <CardBody>
              <BarList
                rows={quality.map((q) => ({
                  label: q.label,
                  value: Math.round(q.score * 100),
                  display: `${Math.round(q.score * 100)}% · ${q.status}`,
                  tone: qualityTone(q.score),
                }))}
              />
            </CardBody>
          </Card>
        </div>

        {/* RIGHT — the intelligence panel */}
        <div className="stack">
          <Card>
            <CardHead
              eyebrow="AI-assisted"
              title="Compliance summary"
              subtitle="Assistance metric — inspectors make the final decision"
            />
            <CardBody>
              <div className="summary-score">
                <span className="summary-score__num">{complianceScore}</span>
                <span className="cell-muted">/ 100 assistance score</span>
              </div>
              <div className="summary-breakdown" style={{ marginTop: 'var(--space-4)' }}>
                {breakdown.map((b) => (
                  <div key={b.label} className="summary-breakdown__item" style={{ background: toneSoft(b.tone) }}>
                    <span className="row" style={{ gap: 6 }}>
                      <span className="badge__dot" style={{ color: toneColor(b.tone) }} aria-hidden />
                      {b.label}
                    </span>
                    <span className="summary-breakdown__count">{b.value}</span>
                  </div>
                ))}
              </div>
              {reviewedIds.size > 0 && (
                <p style={{ marginTop: 'var(--space-3)', fontSize: 'var(--fs-sm)', color: 'var(--tone-positive)' }}>
                  {reviewedIds.size} decision{reviewedIds.size > 1 ? 's' : ''} recorded this session (demo).
                </p>
              )}
            </CardBody>
          </Card>

          <SectionCard
            eyebrow="Extraction"
            title="Detected declarations"
            subtitle="Select a declaration to locate it on the label"
          >
            {declarations.length === 0 ? (
              <EmptyState icon="image" title="No declarations detected" />
            ) : (
              <div className="stack stack--sm">
                {declarations.map((d) => (
                  <DeclarationField
                    key={`${d.field}-${d.value}`}
                    declaration={d}
                    active={Boolean(d.regionId) && d.regionId === selectedRegionId}
                    onClick={() => d.regionId && setSelectedRegionId((cur) => (cur === d.regionId ? null : d.regionId!))}
                  />
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Findings"
            title="Compliance findings"
            subtitle="Open any finding to see the evidence and why it was flagged"
          >
            <div className="stack stack--sm">
              {findings.map((f) => (
                <FindingCard
                  key={f.id}
                  finding={f}
                  active={openFinding?.id === f.id}
                  onOpen={openFindingCard}
                />
              ))}
            </div>
          </SectionCard>
        </div>
      </div>

      {openFinding && (
        <EvidenceDrawer
          finding={openFinding}
          onClose={() => setOpenFinding(null)}
          onReviewed={(findingId) => setReviewedIds((prev) => new Set(prev).add(findingId))}
        />
      )}
    </>
  );
}
