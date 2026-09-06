/**
 * Shared user-display helpers (single copy — previously duplicated across
 * Sidebar, TopBar and Settings).
 */

/** Two-letter initials for avatar chips. */
export function initials(name: string): string {
  const parts = name.replace(/^Dr\.?\s+/i, '').trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '–';
}
