/** Join truthy class-name fragments. Keeps conditional styling readable. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
