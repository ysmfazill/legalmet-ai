import type { Tone } from '@legalmet/config';

/** Resolve a semantic tone to its CSS custom property (for inline SVG/styles). */
export function toneColor(tone: Tone): string {
  return `var(--tone-${tone})`;
}

export function toneSoft(tone: Tone): string {
  return `var(--tone-${tone}-soft)`;
}
