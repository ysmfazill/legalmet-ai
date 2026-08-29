/**
 * WHY chain (Prompt 7, Phase 8) — the six-step human-readable trace.
 *
 * Given a finding's traceability graph, this renders the causal narrative an
 * inspector or auditor reads top-to-bottom:
 *
 *   1. SOURCE  — who published the law (name, jurisdiction, verification)
 *   2. DOCUMENT — which legal instrument
 *   3. VERSION — which version was in force at the context date
 *   4. REQUIREMENT + RULE — what the package must declare and the deterministic
 *      check applied
 *   5. EVIDENCE — what the system actually saw (image → region → OCR → field)
 *   6. FINDING — the system's decision-support output, with evidence strength
 *
 * Every step renders ONLY data extracted from the real graph payload — no step
 * is ever fabricated, and a step whose nodes are absent renders as an honest
 * "not recorded" row rather than a placeholder value.
 */
import {
  EVIDENCE_STRENGTH_META,
} from '@legalmet/config';

import type {
  EvidenceStrength,
  EvidenceTraceGraph,
  Json,
  TraceNode,
} from '@legalmet/types';

import { Icon } from '../components/Icon';
import { humanizeEnum } from '../lib/format';

interface ChainStep {
  key: string;
  title: string;
  lines: Array<{ label: string; value: string }>;
  /** Honest-absence marker: the step exists in the model but has no node. */
  missing?: boolean;
}

function metaOf(node: TraceNode): Record<string, Json> {
  return (node.metadata ?? {}) as Record<string, Json>;
}

function str(m: Record<string, Json>, key: string): string | null {
  const v = m[key];
  return typeof v === 'string' && v !== '' ? v : null;
}

function byType(graph: EvidenceTraceGraph, type: string): TraceNode[] {
  return graph.nodes.filter((n) => n.type === type);
}

function only(graph: EvidenceTraceGraph, type: string): TraceNode | null {
  return byType(graph, type)[0] ?? null;
}

function stepsFor(graph: EvidenceTraceGraph): ChainStep[] {
  const steps: ChainStep[] = [];

  // 1 — Source
  const source = only(graph, 'REGULATORY_SOURCE');
  if (source) {
    const m = metaOf(source);
    steps.push({
      key: 'source',
      title: '1 · Regulatory source',
      lines: [
        { label: 'Publisher', value: str(m, 'name') ?? source.label },
        { label: 'Authority', value: str(m, 'authority') ?? '—' },
        { label: 'Jurisdiction', value: str(m, 'jurisdiction') ?? '—' },
        {
          label: 'Verification',
          value: str(m, 'verificationStatus')
            ? humanizeEnum(str(m, 'verificationStatus')!)
            : '—',
        },
      ],
    });
  } else {
    steps.push({
      key: 'source',
      title: '1 · Regulatory source',
      lines: [],
      missing: true,
    });
  }

  // 2 — Document
  const document = only(graph, 'REGULATORY_DOCUMENT');
  if (document) {
    const m = metaOf(document);
    steps.push({
      key: 'document',
      title: '2 · Legal instrument',
      lines: [
        { label: 'Title', value: str(m, 'title') ?? document.label },
        { label: 'Code', value: str(m, 'code') ?? '—' },
        {
          label: 'Type',
          value: str(m, 'documentType') ? humanizeEnum(str(m, 'documentType')!) : '—',
        },
        { label: 'Identifier', value: str(m, 'documentIdentifier') ?? '—' },
      ],
    });
  } else {
    steps.push({ key: 'document', title: '2 · Legal instrument', lines: [], missing: true });
  }

  // 3 — Version in force
  const version = only(graph, 'REGULATORY_VERSION');
  if (version) {
    const m = metaOf(version);
    steps.push({
      key: 'version',
      title: '3 · Version in force',
      lines: [
        { label: 'Version', value: str(m, 'versionLabel') ?? version.label },
        {
          label: 'Effective',
          value: [
            str(m, 'effectiveFrom')?.slice(0, 10),
            str(m, 'effectiveUntil')?.slice(0, 10),
          ]
            .filter(Boolean)
            .join(' → ') || '—',
        },
        { label: 'Status', value: str(m, 'status') ? humanizeEnum(str(m, 'status')!) : '—' },
      ],
    });
  } else {
    steps.push({ key: 'version', title: '3 · Version in force', lines: [], missing: true });
  }

  // 4 — Requirement + rules
  const requirement = only(graph, 'REQUIREMENT');
  const rules = byType(graph, 'RULE');
  if (requirement || rules.length > 0) {
    const m = requirement ? metaOf(requirement) : {};
    steps.push({
      key: 'requirement',
      title: '4 · Requirement & deterministic rule',
      lines: [
        {
          label: 'Requirement',
          value: requirement
            ? [str(m, 'ruleCode'), str(m, 'title')].filter(Boolean).join(' — ')
            : '—',
        },
        ...(requirement && str(m, 'sourceReference')
          ? [{ label: 'Reference', value: str(m, 'sourceReference')! }]
          : []),
        {
          label: 'Rules applied',
          value:
            rules.length > 0
              ? rules
                  .map((r) => {
                    const rm = metaOf(r);
                    const code = str(rm, 'ruleCode') ?? r.label;
                    const active = rm.active;
                    return active === false ? `${code} (now inactive)` : code;
                  })
                  .join(', ')
              : 'None recorded on this trace',
        },
      ],
    });
  } else {
    steps.push({
      key: 'requirement',
      title: '4 · Requirement & deterministic rule',
      lines: [],
      missing: true,
    });
  }

  // 5 — Evidence (image → region → OCR → field)
  const images = byType(graph, 'IMAGE');
  const regions = byType(graph, 'IMAGE_REGION');
  const ocrs = byType(graph, 'OCR_RESULT');
  const fields = byType(graph, 'EXTRACTED_FIELD');
  if (images.length + regions.length + ocrs.length + fields.length > 0) {
    const firstOcr = ocrs[0] ? metaOf(ocrs[0]) : null;
    const firstField = fields[0] ? metaOf(fields[0]) : null;
    steps.push({
      key: 'evidence',
      title: '5 · Evidence perceived by the system',
      lines: [
        {
          label: 'Image',
          value:
            images.length > 0
              ? images
                  .map((img) => str(metaOf(img), 'filename') ?? img.label)
                  .join(', ')
              : 'No image node on this trace',
        },
        { label: 'Regions', value: String(regions.length) },
        {
          label: 'OCR text (verbatim)',
          value: firstOcr && str(firstOcr, 'rawText') ? `“${str(firstOcr, 'rawText')}”` : '—',
        },
        {
          label: 'Extracted value',
          value: firstField && str(firstField, 'normalizedValue') !== null
            ? str(firstField, 'normalizedValue')!
            : 'No usable value read',
        },
        {
          label: 'OCR confidence',
          value:
            firstOcr && typeof firstOcr.confidence === 'number'
              ? `${(firstOcr.confidence * 100).toFixed(1)}% (recognition score — not legal confidence)`
              : '—',
        },
      ],
    });
  } else {
    steps.push({
      key: 'evidence',
      title: '5 · Evidence perceived by the system',
      lines: [
        {
          label: 'Evidence',
          value: 'No evidence node — this is NOT evidence of absence and never a violation',
        },
      ],
      missing: true,
    });
  }

  // 6 — Finding
  const finding = only(graph, 'FINDING');
  if (finding) {
    const m = metaOf(finding);
    const strength = str(m, 'evidenceStrength') as EvidenceStrength | null;
    const strengthMeta = strength ? EVIDENCE_STRENGTH_META[strength] : null;
    steps.push({
      key: 'finding',
      title: '6 · System finding',
      lines: [
        { label: 'Status', value: str(m, 'status') ? humanizeEnum(str(m, 'status')!) : '—' },
        { label: 'Detected', value: str(m, 'detectedValue') ?? 'Nothing detected' },
        { label: 'Expected', value: str(m, 'expectedValue') ?? '—' },
        {
          label: 'Evidence strength',
          value: strengthMeta
            ? `${strengthMeta.label} — ${strengthMeta.description}`
            : 'Not computed',
        },
      ],
    });
  } else {
    steps.push({ key: 'finding', title: '6 · System finding', lines: [], missing: true });
  }

  return steps;
}

export function WhyChain({ graph }: { graph: EvidenceTraceGraph }) {
  const steps = stepsFor(graph);
  return (
    <ol className="why-chain">
      {steps.map((step) => (
        <li key={step.key} className={step.missing ? 'why-chain__step is-missing' : 'why-chain__step'}>
          <div className="why-chain__head">
            <span className="why-chain__title">{step.title}</span>
          </div>
          {step.missing ? (
            <p className="why-chain__missing">
              <Icon name="info" size={14} />
              Not recorded on this trace — reported honestly rather than filled in.
            </p>
          ) : (
            <dl className="why-chain__lines">
              {step.lines.map((line) => (
                <div key={line.label} className="why-chain__line">
                  <dt>{line.label}</dt>
                  <dd>{line.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ol>
  );
}
