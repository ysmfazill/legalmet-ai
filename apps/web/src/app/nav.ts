import type { User } from '@legalmet/types';
import type { IconName } from '../components/Icon';

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Dynamic badge source resolved by the Sidebar. */
  badge?: 'review';
  /** Match the route exactly (for the index route). */
  end?: boolean;
  /**
   * Roles allowed to see this destination. Absent = any authenticated user.
   * Mirrors backend RBAC (services/api/app/api/routers/*) so unauthorized
   * navigation is never offered.
   */
  roles?: readonly User['role'][];
}

const WRITE_ROLES: readonly User['role'][] = ['ADMIN', 'INSPECTOR', 'SUPERVISOR'];
const AUDIT_ROLES: readonly User['role'][] = ['ADMIN', 'AUDITOR', 'SUPERVISOR'];
const STAFF_ROLES: readonly User['role'][] = ['ADMIN', 'INSPECTOR', 'SUPERVISOR', 'AUDITOR'];

/** Primary destinations of the inspection platform. */
export const PRIMARY_NAV: NavItem[] = [
  { to: '/dashboard', label: 'Command Center', icon: 'dashboard' },
  { to: '/inspections', label: 'Inspections', icon: 'inspections' },
  { to: '/complaints', label: 'Complaints', icon: 'complaints' },
  { to: '/review', label: 'Review Queue', icon: 'review', badge: 'review' },
  { to: '/evidence', label: 'Evidence Explorer', icon: 'evidence' },
  { to: '/regulations', label: 'Regulatory Intelligence', icon: 'regulations' },
  { to: '/batches', label: 'Batch Intelligence', icon: 'batch' },
  { to: '/risk', label: 'Risk Radar', icon: 'risk' },
  { to: '/reports', label: 'Reports', icon: 'reports' },
  // UI-09 — search, history & operational intelligence (read-only).
  { to: '/history', label: 'Inspection History', icon: 'clock' },
  { to: '/products', label: 'Product Repository', icon: 'package' },
  { to: '/analytics', label: 'Operational Intelligence', icon: 'scale' },
];

export const WORKSPACE_NAV: NavItem[] = [
  { to: '/department', label: 'Department Command Center', icon: 'department', roles: STAFF_ROLES },
  { to: '/inspector', label: 'Inspector Workspace', icon: 'inspections', roles: WRITE_ROLES },
];

export const SYSTEM_NAV: NavItem[] = [
  { to: '/audit', label: 'Audit Trail', icon: 'audit', roles: AUDIT_ROLES },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];

/** Citizen Mode — public-facing experience, always reachable. */
export const CITIZEN_NAV: NavItem[] = [{ to: '/citizen', label: 'Citizen Mode', icon: 'citizen' }];

/** Filter a nav list down to destinations the given role may see. */
export function navFor(list: NavItem[], role: User['role']): NavItem[] {
  return list.filter((item) => !item.roles || item.roles.includes(role));
}

export interface PageMeta {
  title: string;
  breadcrumb: string[];
}

/** Resolve the top-bar title + breadcrumb for a pathname (TopBar is outside Routes). */
export function resolvePage(pathname: string): PageMeta {
  if (pathname === '/' || pathname.startsWith('/login'))
    return { title: 'Welcome', breadcrumb: ['METRASIGHT'] };
  if (pathname === '/dashboard')
    return { title: 'Command Center', breadcrumb: ['Command Center'] };
  if (pathname === '/inspections/new')
    return { title: 'New Inspection', breadcrumb: ['Inspections', 'New'] };
  if (/^\/inspections\/[^/]+$/.test(pathname))
    return { title: 'Inspection Workspace', breadcrumb: ['Inspections', 'Workspace'] };
  if (pathname.startsWith('/inspections')) return { title: 'Inspections', breadcrumb: ['Inspections'] };
  if (pathname.startsWith('/complaints'))
    return { title: 'Complaint Management', breadcrumb: ['Complaints'] };
  if (pathname.startsWith('/review')) return { title: 'Review Queue', breadcrumb: ['Review Queue'] };
  if (pathname.startsWith('/evidence'))
    return { title: 'Evidence Explorer', breadcrumb: ['Evidence Explorer'] };
  if (pathname.startsWith('/regulations'))
    return { title: 'Regulatory Intelligence', breadcrumb: ['Regulatory Intelligence'] };
  if (pathname.startsWith('/batches'))
    return { title: 'Batch Intelligence', breadcrumb: ['Batch Intelligence'] };
  if (pathname.startsWith('/risk')) return { title: 'Risk Radar', breadcrumb: ['Risk Radar'] };
  if (pathname.startsWith('/reports')) return { title: 'Reports', breadcrumb: ['Reports'] };
  if (/^\/products\/[^/]+$/.test(pathname))
    return { title: 'Product Detail', breadcrumb: ['Product Repository', 'Product'] };
  if (pathname.startsWith('/products'))
    return { title: 'Product Repository', breadcrumb: ['Product Repository'] };
  if (pathname.startsWith('/history'))
    return { title: 'Inspection History', breadcrumb: ['Inspection History'] };
  if (pathname.startsWith('/analytics'))
    return { title: 'Operational Intelligence', breadcrumb: ['Operational Intelligence'] };
  if (pathname.startsWith('/audit')) return { title: 'Audit Trail', breadcrumb: ['Audit Trail'] };
  if (pathname.startsWith('/settings')) return { title: 'Settings', breadcrumb: ['Settings'] };
  if (pathname.startsWith('/citizen')) return { title: 'Citizen Mode', breadcrumb: ['Citizen Mode'] };
  if (pathname.startsWith('/department'))
    return { title: 'Department Command Center', breadcrumb: ['Department'] };
  if (pathname.startsWith('/inspector'))
    return { title: 'Inspector Workspace', breadcrumb: ['Inspector'] };
  return { title: 'Not Found', breadcrumb: ['Not Found'] };
}
