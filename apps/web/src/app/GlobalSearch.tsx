/**
 * UI-09 §2-§5 — GLOBAL SEARCH, wired into the TopBar.
 *
 * One command-style input searching inspections, complaints, products,
 * reports, findings and evidence — server-side, debounced, RBAC-aware.
 * Every hit cross-links to an EXISTING detail page; no duplicate pages are
 * created here. Results never carry citizen reporter PII (the backend does
 * not select it — privacy by construction, §28).
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import type {
  SearchComplaintHit,
  SearchEvidenceHit,
  SearchFindingHit,
  SearchInspectionHit,
  SearchProductHit,
  SearchReportHit,
  SearchResults,
} from '@legalmet/types';

import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { SearchBar } from '../components/inputs';
import { useApp } from './AppContext';

const DEBOUNCE_MS = 300;
/** §3: sensible minimum — shorter queries are trimmed/noise server-side. */
const MIN_QUERY = 2;

function HitRow({
  title,
  meta,
  to,
  onNavigate,
}: {
  title: string;
  meta: string;
  to: string;
  onNavigate: () => void;
}) {
  return (
    <Link className="gsearch__hit" to={to} onClick={onNavigate}>
      <span className="gsearch__hit-title">{title}</span>
      <span className="gsearch__hit-meta">{meta}</span>
    </Link>
  );
}

function inspectionHit(h: SearchInspectionHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={h.reference}
      meta={`${h.productName ?? 'No product'} · ${h.inspectorName ?? 'Unassigned'}`}
      to={`/inspections/${h.id}`}
      onNavigate={close}
    />
  );
}

function complaintHit(h: SearchComplaintHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={h.reference}
      meta={`${h.product} — ${h.issue}${h.location ? ` · ${h.location}` : ''}`}
      to={`/complaints/${h.id}`}
      onNavigate={close}
    />
  );
}

function productHit(h: SearchProductHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={h.name}
      meta={`${h.inspectionCount} inspection${h.inspectionCount === 1 ? '' : 's'}${
        h.gtin ? ` · GTIN ${h.gtin}` : ''
      }`}
      to={`/products/${h.id}`}
      onNavigate={close}
    />
  );
}

function reportHit(h: SearchReportHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={`${h.inspectionReference} — report v${h.version}`}
      meta={h.status}
      to={`/reports/${h.id}`}
      onNavigate={close}
    />
  );
}

/** Findings/evidence live inside their inspection — link there (§4/§5). */
function findingHit(h: SearchFindingHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={h.ruleCode ?? h.detectedValue ?? 'Finding'}
      meta={`${h.inspectionReference} · ${h.status}${h.detectedValue ? ` · ${h.detectedValue}` : ''}`}
      to={`/inspections/${h.inspectionId}`}
      onNavigate={close}
    />
  );
}

function evidenceHit(h: SearchEvidenceHit, close: () => void) {
  return (
    <HitRow
      key={h.id}
      title={h.value}
      meta={`${h.inspectionReference} · ${h.fieldType}`}
      to={`/inspections/${h.inspectionId}`}
      onNavigate={close}
    />
  );
}

export function GlobalSearch() {
  const { isLive } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // §29: debounce the input — one request per pause, not per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  const searchable = isLive && debounced.length >= MIN_QUERY;

  useEffect(() => {
    if (!searchable) {
      setResults(null);
      setError(false);
      return;
    }
    let cancelled = false;
    setOpen(true);
    setError(false);
    api
      .search({ q: debounced, limit: 5 })
      .then((r) => {
        if (!cancelled) setResults(r);
      })
      .catch(() => {
        if (!cancelled) {
          setResults(null);
          setError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchable, debounced]);

  // Close on outside click / Escape.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  function close() {
    setOpen(false);
  }

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    setOpen(false);
    navigate(q ? `/history?q=${encodeURIComponent(q)}` : '/history');
  }

  const trimmed = query.trim();
  const showPanel = open;
  const groups: Array<{
    head: string;
    hits: React.ReactNode[];
  }> = results
    ? [
        { head: 'Inspections', hits: results.inspections.map((h) => inspectionHit(h, close)) },
        { head: 'Complaints', hits: results.complaints.map((h) => complaintHit(h, close)) },
        { head: 'Products', hits: results.products.map((h) => productHit(h, close)) },
        { head: 'Reports', hits: results.reports.map((h) => reportHit(h, close)) },
        { head: 'Findings', hits: results.findings.map((h) => findingHit(h, close)) },
        { head: 'Evidence', hits: results.evidence.map((h) => evidenceHit(h, close)) },
      ].filter((g) => g.hits.length > 0)
    : [];

  return (
    <div className="gsearch" ref={rootRef}>
      <form onSubmit={submitSearch} role="search">
        <SearchBar
          value={query}
          onChange={(v) => {
            setQuery(v);
            setOpen(true);
          }}
          placeholder="Search inspections, complaints, products, reports or evidence..."
          ariaLabel="Global search"
        />
      </form>
      {showPanel && (
        <div className="gsearch__panel" role="listbox" aria-label="Search results">
          {error ? (
            <div className="gsearch__foot" role="alert">
              Unable to load search results.
            </div>
          ) : !isLive ? (
            <div className="gsearch__foot">Backend unavailable — connect the API to search.</div>
          ) : trimmed.length < MIN_QUERY ? (
            <div className="gsearch__foot">
              Type at least {MIN_QUERY} characters to search.
            </div>
          ) : !results ? (
            <div className="gsearch__foot">Searching…</div>
          ) : groups.length === 0 ? (
            <div className="gsearch__foot">No matching records.</div>
          ) : (
            <>
              {groups.map((g) => (
                <div className="gsearch__group" key={g.head}>
                  <div className="gsearch__group-head">{g.head}</div>
                  {g.hits}
                </div>
              ))}
              <div className="gsearch__foot">
                <Icon name="search" size={11} /> Press Enter for full inspection history
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
