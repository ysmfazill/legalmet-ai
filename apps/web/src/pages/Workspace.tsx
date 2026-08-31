import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

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
import {
  ComplianceControlCard,
  ComplianceFindingsCard,
} from '../compliance/CompliancePanel';
import { FindingExplanationDrawer } from '../compliance/FindingExplanationDrawer';
import { useCompliance } from '../compliance/useCompliance';
import { FinalDecisionCard } from '../hitl/FinalDecisionCard';
import { useHitl } from '../hitl/useHitl';
import { EvidenceTraceCard } from '../evidence/EvidenceTraceCard';
import { QualityReadout } from '../intake/QualityReadout';
import { FieldEvidenceDrawer } from '../perception/FieldEvidenceDrawer';
import {
  PerceptionControlCard,
  PerceptionDeclarationsCard,
  PerceptionRunHistoryCard,
} from '../perception/PerceptionPanel';
import { PerceptionViewer } from '../perception/PerceptionViewer';
import { usePerception } from '../perception/usePerception';
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
/* REAL inspection workspace — actual uploaded image + REAL perception        */
/* (Prompt 4).                                                                */
/*                                                                            */
/* Shows what the system PERCEIVED: real OCR text, symbol regions and         */
/* extracted declaration candidates with full evidence links. It never shows  */
/* a compliance verdict — the strongest statement available is                */
/* "awaiting regulatory evaluation".                                          */
/* -------------------------------------------------------------------------- */
function RealInspectionWorkspace({ inspection }: { inspection: Inspection }) {
  const images = inspection.packages?.flatMap((p) => p.images ?? []) ?? [];
  const statusMeta = INSPECTION_STATUS_META[inspection.status];
  const isReady = inspection.status === 'READY_FOR_ANALYSIS';
  // Deep link from Evidence Explorer: ?field=<extractedFieldId> opens the
  // evidence drawer for that field and highlights its region on the image.
  const [searchParams] = useSearchParams();
  const deepLinkFieldId = searchParams.get('field');

  const perception = usePerception(inspection.id);
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [openFindingId, setOpenFindingId] = useState<string | null>(null);

  // Once perception data loads, resolve the deep-linked field exactly once.
  const appliedDeepLink = useRef<string | null>(null);
  useEffect(() => {
    if (!deepLinkFieldId || appliedDeepLink.current === deepLinkFieldId) return;
    if (perception.loading) return;
    if (perception.fields.some((f) => f.id === deepLinkFieldId)) {
      appliedDeepLink.current = deepLinkFieldId;
      setSelectedFieldId(deepLinkFieldId);
    }
  }, [deepLinkFieldId, perception.loading, perception.fields]);

  const hasRuns = perception.analysis?.hasRuns ?? false;

  const compliance = useCompliance(inspection.id, hasRuns);
  const hitl = useHitl(inspection.id, hasRuns);
  const openFinding =
    compliance.findings.find((f) => f.id === openFindingId) ?? null;

  const selectedField =
    perception.fields.find((f) => f.id === selectedFieldId) ?? null;
  const selectedRegionId = selectedField?.imageRegionId ?? null;
  const selectedOcrLine = selectedField?.sourceOcrResultId
    ? perception.ocr.find((o) => o.id === selectedField.sourceOcrResultId) ?? null
    : null;
  const selectedRegion = selectedField?.imageRegionId
    ? perception.regions.find((r) => r.id === selectedField.imageRegionId) ?? null
    : null;
  const selectedRun = selectedField?.processingRunId
    ? perception.runs.find((r) => r.id === selectedField.processingRunId) ?? null
    : null;

  return (
    <>
      <PageHeader
        eyebrow={inspection.referenceNo}
        title={inspection.product?.name ?? 'Packaged commodity'}
        lead={`${inspection.product?.category ?? '—'} · Real package perception`}
        actions={
          <>
            <span className="tag tag--live" title="This inspection was created through real intake and lives in the backend database">
              LIVE INSPECTION
            </span>
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
        <Icon name="info" size={15} />
        <span>
          <strong>{statusMeta?.label ?? humanizeEnum(inspection.status)}.</strong>{' '}
          {isReady
            ? 'Images are validated and stored. '
            : 'Images are validated and stored with a deterministic usability grade. '}
          Perception results below come from <strong>real OCR and symbol detection</strong> over the
          uploaded pixels — they describe what the system <em>saw</em>, not whether the package is
          legally compliant.
        </span>
      </div>

      {perception.error && (
        <div className="demo-note demo-note--block" style={{ borderColor: 'var(--tone-critical)' }}>
          <Icon name="alert" size={15} />
          <span>Could not load perception data: {perception.error}</span>
        </div>
      )}

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
        <div className="split">
          {/* LEFT — the real package images with perception overlays */}
          <div className="stack">
            {images.map((image) => (
              <div className="stack" key={image.id}>
                <PerceptionViewer
                  image={image}
                  ocrLines={perception.ocr.filter((o) => o.imageId === image.id)}
                  symbolRegions={perception.regions.filter(
                    (r) =>
                      r.imageId === image.id &&
                      (r.regionType === 'QR_CODE' || r.regionType === 'BARCODE'),
                  )}
                  selectedRegionId={selectedRegionId}
                />
                <RealImageMeta image={image} />
              </div>
            ))}
          </div>

          {/* RIGHT — the perception + compliance panels */}
          <div className="stack">
            <PerceptionControlCard
              analysis={perception.analysis}
              starting={perception.starting}
              hasImages={images.length > 0}
              runs={perception.runs}
              hasEvaluation={Boolean(compliance.evaluation)}
              onStart={() => void perception.start()}
            />

            {hasRuns && (
              <div className="demo-note demo-note--block">
                <Icon name="scale" size={15} />
                <span>
                  <strong>Perception ≠ compliance.</strong> The declarations card lists what the
                  system detected. The deterministic engine below checks each requirement in force
                  against that evidence — every conclusion is traceable, and the inspector makes the
                  final decision.
                </span>
              </div>
            )}

            <PerceptionDeclarationsCard
              fields={perception.fields}
              selectedFieldId={selectedFieldId}
              onSelect={(field) =>
                setSelectedFieldId((cur) => (cur === field.id ? null : field.id))
              }
            />

            {hasRuns && (
              <>
                <ComplianceControlCard
                  evaluation={compliance.evaluation}
                  evaluating={compliance.evaluating}
                  error={compliance.error}
                  hasEvidence={perception.fields.length > 0}
                  onEvaluate={() => void compliance.evaluate()}
                />
                {compliance.findings.length > 0 && (
                  <ComplianceFindingsCard
                    findings={compliance.findings}
                    selectedFindingId={openFindingId}
                    onOpen={(finding) =>
                      setOpenFindingId((cur) => (cur === finding.id ? null : finding.id))
                    }
                  />
                )}
                <EvidenceTraceCard
                  inspectionId={inspection.id}
                  evaluationId={compliance.evaluation?.id ?? null}
                  hasEvaluation={Boolean(compliance.evaluation)}
                />
                <FinalDecisionCard
                  hitl={hitl}
                  hasFindings={compliance.findings.length > 0}
                />
              </>
            )}

            <PerceptionRunHistoryCard
              runs={perception.runs}
              onReanalyze={(imageId) => void perception.reanalyze(imageId)}
              reanalyzing={perception.starting}
            />
          </div>
        </div>
      )}

      {selectedField && (
        <FieldEvidenceDrawer
          field={selectedField}
          inspectionId={inspection.id}
          ocrLine={selectedOcrLine}
          region={selectedRegion}
          run={selectedRun}
          onClose={() => setSelectedFieldId(null)}
        />
      )}

      {openFinding && (
        <FindingExplanationDrawer
          finding={openFinding}
          onClose={() => setOpenFindingId(null)}
          hitl={hitl}
          onReviewed={() => void compliance.reload()}
        />
      )}
    </>
  );
}

/** Provenance + usability metadata for one real stored image. */
function RealImageMeta({ image }: { image: PackageImage }) {
  const resolution =
    image.width && image.height ? `${image.width} × ${image.height}` : 'Pending';
  const score =
    image.qualityScore != null ? `${Math.round(image.qualityScore * 100)}/100` : '—';
  const shortChecksum = image.checksum ? `${image.checksum.slice(0, 12)}…` : '—';

  return (
    <>
      <SectionCard
        eyebrow="Provenance"
        title={image.originalFilename}
        subtitle="Real stored image — metadata and usability only."
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
    </>
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
