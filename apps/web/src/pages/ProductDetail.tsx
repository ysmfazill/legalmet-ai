/**
 * UI-09 §10-§11 — PRODUCT DETAIL (the historical record).
 *
 * Overview + declared fields, inspection history, recurring findings (worded
 * neutrally — a "Repeated inspection finding", never a violator label), and
 * the evidence gallery linking back to the originating inspections.
 *
 * Honesty contract (§11): previous inspections do NOT prove current
 * compliance. The boundary note from the backend is always rendered.
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  FIELD_TYPE_LABELS,
  REPORT_RESULT_META,
  REPORT_STATUS_META,
} from '@legalmet/config';
import type {
  ProductDetail,
  ProductEvidenceImage,
  ProductFindingHistory,
  ProductInspectionRef,
} from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState, ErrorState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDate, humanizeEnum } from '../lib/format';

function resultTone(result: string): Tone {
  return (REPORT_RESULT_META[result] ?? { tone: 'neutral' }).tone;
}

function resultLabel(result: string): string {
  return REPORT_RESULT_META[result]?.label ?? humanizeEnum(result);
}

function fieldLabel(fieldType: string): string {
  return (
    FIELD_TYPE_LABELS[fieldType as keyof typeof FIELD_TYPE_LABELS] ??
    humanizeEnum(fieldType)
  );
}

function reportStatusLabel(status: string): string {
  return (
    (REPORT_STATUS_META as Record<string, { label: string }>)[status]?.label ??
    humanizeEnum(status)
  );
}

/** §10: inspection history rows — real references, real results. */
function inspectionColumns(): Column<ProductInspectionRef>[] {
  return [
    {
      key: 'reference',
      header: 'Inspection',
      render: (r) => (
        <Link className="cell-strong" to={`/inspections/${r.id}`}>
          {r.reference}
        </Link>
      ),
    },
    {
      key: 'date',
      header: 'Date',
      render: (r) => <span className="cell-muted">{formatDate(r.createdAt)}</span>,
    },
    {
      key: 'inspector',
      header: 'Inspector',
      render: (r) => r.inspectorName ?? <span className="cell-muted">—</span>,
    },
    {
      key: 'source',
      header: 'Source',
      render: (r) => (
        <Badge tone={r.source === 'CITIZEN_COMPLAINT' ? 'info' : 'neutral'} outline>
          {r.source === 'CITIZEN_COMPLAINT' ? 'Citizen Complaint' : 'Direct Inspection'}
        </Badge>
      ),
    },
    {
      key: 'result',
      header: 'Result',
      render: (r) => (
        <Badge tone={resultTone(r.result)}>{resultLabel(r.result)}</Badge>
      ),
    },
    {
      key: 'report',
      header: 'Report',
      render: (r) =>
        r.report ? (
          <Link className="btn btn--subtle btn--sm" to={`/reports/${r.report.id}`}>
            {reportStatusLabel(r.report.status)} · v{r.report.version}
          </Link>
        ) : (
          <span className="cell-muted">—</span>
        ),
    },
  ];
}

/** §11: recurring findings — neutral, historical wording only. */
function findingColumns(): Column<ProductFindingHistory>[] {
  return [
    {
      key: 'rule',
      header: 'Requirement',
      render: (f) => (
        <div>
          <span className="cell-strong">{f.ruleCode ?? 'Requirement'}</span>
          <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {f.label}
          </div>
        </div>
      ),
    },
    {
      key: 'occurrences',
      header: 'Occurrences',
      render: (f) => f.occurrenceCount,
    },
    {
      key: 'inspections',
      header: 'Inspections',
      render: (f) => f.inspectionCount,
    },
    {
      key: 'review',
      header: 'Review Required',
      render: (f) => f.reviewRequiredCount,
    },
    {
      key: 'nonCompliant',
      header: 'Non-Compliant',
      render: (f) => f.nonCompliantCount,
    },
  ];
}

function GalleryImage({ image }: { image: ProductEvidenceImage }) {
  return (
    <Link className="pgallery__card" to={`/inspections/${image.inspectionId}`}>
      <span className="pgallery__thumb" aria-hidden>
        <Icon name="image" size={26} />
      </span>
      <span className="pgallery__name">{image.originalFilename}</span>
      <span className="pgallery__meta">
        {image.inspectionReference} · {formatDate(image.createdAt)}
      </span>
      {image.fieldTypes.length > 0 && (
        <span className="pgallery__chips">
          {image.fieldTypes.slice(0, 4).map((t) => (
            <Badge key={t} tone="info" outline>
              {fieldLabel(t)}
            </Badge>
          ))}
        </span>
      )}
    </Link>
  );
}

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isLive } = useApp();

  const query = useAsync(
    () => (isLive && id ? api.getProduct(id) : Promise.resolve(null)),
    [isLive, id],
  );

  const inspectionCols = useMemo(inspectionColumns, []);
  const findingCols = useMemo(findingColumns, []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Product Repository"
        title="Product Detail"
        lead="Historical inspection record — previous inspections do not prove current compliance."
        actions={
          <Link className="btn btn--subtle" to="/products">
            <Icon name="chevronLeft" size={15} />
            Back to Product Repository
          </Link>
        }
      />

      {!isLive ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="alert"
              title="Backend unavailable"
              message="Product history is real, database-backed data and requires the live backend."
            />
          </CardBody>
        </Card>
      ) : (
        <AsyncView query={query} loadingLabel="Loading product history…">
          {(product: ProductDetail | null) =>
            product ? (
              <>
                <div className="grid grid--metrics">
                  <MetricCard label="Inspections" value={product.inspectionCount} icon="inspections" />
                  <MetricCard label="Findings" value={product.findingCount} icon="review" />
                  <MetricCard
                    label="Last Inspected"
                    value={product.lastInspectionAt ? formatDate(product.lastInspectionAt) : 'Never'}
                    icon="clock"
                  />
                  <MetricCard
                    label="Latest Result"
                    value={resultLabel(product.latestResult)}
                    icon="scale"
                    hint={formatDate(product.lastInspectionAt)}
                  />
                </div>

                {/* The honesty contract, verbatim from the backend (§11). */}
                <Card>
                  <CardBody>
                    <div className="row" style={{ gap: 'var(--space-2)', alignItems: 'center' }}>
                      <Icon name="info" size={16} />
                      <span>{product.boundaryNote}</span>
                    </div>
                  </CardBody>
                </Card>

                <Card>
                  <CardHead
                    title={product.name}
                    subtitle={`${product.category}${product.gtin ? ` · GTIN ${product.gtin}` : ''}`}
                  />
                  <CardBody>
                    <div className="eyebrow">Latest detected declarations</div>
                    {product.declaredFields.length > 0 ? (
                      <DataTable
                        columns={[
                          {
                            key: 'field',
                            header: 'Field',
                            render: (f) => fieldLabel(f.fieldType),
                          },
                          {
                            key: 'value',
                            header: 'Detected Value',
                            render: (f) => (
                              <span>
                                {f.normalizedValue ?? f.rawText}
                                {f.unit ? ` ${f.unit}` : ''}
                              </span>
                            ),
                          },
                          {
                            key: 'inspection',
                            header: 'From Inspection',
                            render: (f) => (
                              <Link to={`/inspections/${f.inspectionId}`}>
                                {f.inspectionReference}
                              </Link>
                            ),
                          },
                          {
                            key: 'at',
                            header: 'Detected',
                            render: (f) => (
                              <span className="cell-muted">{formatDate(f.detectedAt)}</span>
                            ),
                          },
                        ]}
                        rows={product.declaredFields}
                        getRowId={(f) => f.inspectionId + f.fieldType}
                        ariaLabel="Declared fields"
                      />
                    ) : (
                      <p className="cell-muted">No declared fields detected yet.</p>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHead title="Inspection history" subtitle="Every recorded inspection of this product." />
                  <CardBody flush>
                    {product.inspections.length > 0 ? (
                      <DataTable
                        columns={inspectionCols}
                        rows={product.inspections}
                        getRowId={(r) => r.id}
                        ariaLabel="Product inspection history"
                      />
                    ) : (
                      <div style={{ padding: 'var(--space-4)' }}>
                        <EmptyState
                          icon="inspections"
                          title="No inspections recorded."
                          message="This product has no inspection history yet."
                        />
                      </div>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHead
                    title="Repeated inspection findings"
                    subtitle="A historical pattern — not a verdict on the current package."
                  />
                  <CardBody flush>
                    {product.findingsHistory.length > 0 ? (
                      <DataTable
                        columns={findingCols}
                        rows={product.findingsHistory}
                        getRowId={(f) => f.ruleCode ?? f.label}
                        ariaLabel="Repeated inspection findings"
                      />
                    ) : (
                      <div style={{ padding: 'var(--space-4)' }}>
                        <EmptyState
                          icon="check"
                          title="No repeated findings."
                          message="No requirement has been flagged on more than one inspection of this product."
                        />
                      </div>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHead
                    title="Evidence gallery"
                    subtitle="Package images captured across inspections — open them in their inspection workspace."
                  />
                  <CardBody>
                    {product.evidenceGallery.length > 0 ? (
                      <div className="pgallery">
                        {product.evidenceGallery.map((image) => (
                          <GalleryImage key={image.id} image={image} />
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        icon="image"
                        title="No package images."
                        message="No evidence images have been captured for this product yet."
                      />
                    )}
                  </CardBody>
                </Card>
              </>
            ) : (
              <ErrorState
                title="Product not found"
                error="This product does not exist or has no recorded activity."
              />
            )
          }
        </AsyncView>
      )}
    </div>
  );
}
