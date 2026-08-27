import type { IconName } from '../components/Icon';

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Dynamic badge source resolved by the Sidebar. */
  badge?: 'review';
  /** Match the route exactly (for the index route). */
  end?: boolean;
}

/** The 10 primary destinations of the inspection platform. */
export const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Command Center', icon: 'dashboard', end: true },
  { to: '/inspections', label: 'Inspections', icon: 'inspections' },
  { to: '/review', label: 'Review Queue', icon: 'review', badge: 'review' },
  { to: '/evidence', label: 'Evidence Explorer', icon: 'evidence' },
  { to: '/regulations', label: 'Regulatory Intelligence', icon: 'regulations' },
  { to: '/batches', label: 'Batch Intelligence', icon: 'batch' },
  { to: '/risk', label: 'Risk Radar', icon: 'risk' },
  { to: '/reports', label: 'Reports', icon: 'reports' },
  { to: '/audit', label: 'Audit Trail', icon: 'audit' },
];

export const SYSTEM_NAV: NavItem[] = [{ to: '/settings', label: 'Settings', icon: 'settings' }];

export interface PageMeta {
  title: string;
  breadcrumb: string[];
}

/** Resolve the top-bar title + breadcrumb for a pathname (TopBar is outside Routes). */
export function resolvePage(pathname: string): PageMeta {
  if (pathname === '/') return { title: 'Command Center', breadcrumb: ['Command Center'] };
  if (pathname === '/inspections/new')
    return { title: 'New Inspection', breadcrumb: ['Inspections', 'New'] };
  if (/^\/inspections\/[^/]+$/.test(pathname))
    return { title: 'Inspection Workspace', breadcrumb: ['Inspections', 'Workspace'] };
  if (pathname.startsWith('/inspections')) return { title: 'Inspections', breadcrumb: ['Inspections'] };
  if (pathname.startsWith('/review')) return { title: 'Review Queue', breadcrumb: ['Review Queue'] };
  if (pathname.startsWith('/evidence'))
    return { title: 'Evidence Explorer', breadcrumb: ['Evidence Explorer'] };
  if (pathname.startsWith('/regulations'))
    return { title: 'Regulatory Intelligence', breadcrumb: ['Regulatory Intelligence'] };
  if (pathname.startsWith('/batches'))
    return { title: 'Batch Intelligence', breadcrumb: ['Batch Intelligence'] };
  if (pathname.startsWith('/risk')) return { title: 'Risk Radar', breadcrumb: ['Risk Radar'] };
  if (pathname.startsWith('/reports')) return { title: 'Reports', breadcrumb: ['Reports'] };
  if (pathname.startsWith('/audit')) return { title: 'Audit Trail', breadcrumb: ['Audit Trail'] };
  if (pathname.startsWith('/settings')) return { title: 'Settings', breadcrumb: ['Settings'] };
  return { title: 'Not Found', breadcrumb: ['Not Found'] };
}
