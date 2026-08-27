/**
 * Client-side intake constants + validation.
 *
 * These mirror the backend limits (`services/api/app/core/config.py`) but exist
 * ONLY to give fast UX feedback. The server re-validates every byte and is the
 * sole authority — never trust these values for a security or correctness
 * decision. See docs/image-quality.md.
 */
import type { CaptureSource, ImageType } from '@legalmet/types';

/** Accepted image MIME types (server-authoritative allowlist mirror). */
export const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;

/** `accept` attribute for file inputs. */
export const ACCEPT_ATTR = ACCEPTED_MIME_TYPES.join(',');

/** 15 MB — mirrors `settings.max_image_size`. */
export const MAX_IMAGE_BYTES = 15 * 1024 * 1024;

/** Mirrors `settings.min_image_width` / `min_image_height`. */
export const MIN_IMAGE_DIMENSION = 400;

/** Mirrors `settings.max_batch_files`. */
export const MAX_BATCH_FILES = 20;

/** Image-type options offered in the intake UI. */
export const IMAGE_TYPE_OPTIONS: { value: ImageType; label: string }[] = [
  { value: 'FRONT', label: 'Front label' },
  { value: 'BACK', label: 'Back label' },
  { value: 'SIDE', label: 'Side panel' },
  { value: 'TOP', label: 'Top' },
  { value: 'BOTTOM', label: 'Bottom' },
  { value: 'LABEL', label: 'Label (other)' },
  { value: 'OTHER', label: 'Other' },
];

/** Product categories offered when creating a real inspection. */
export const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: 'food', label: 'Food' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'cosmetics', label: 'Cosmetics' },
  { value: 'household', label: 'Household' },
  { value: 'electronics', label: 'Electronics' },
  { value: 'general', label: 'General' },
];

export interface ClientValidation {
  ok: boolean;
  /** UX-facing reason when `ok` is false. */
  reason?: string;
}

/**
 * Cheap pre-flight check before spending bandwidth on an upload. Only inspects
 * the client-reported type/size; dimensions and true format are verified
 * server-side from the decoded bytes.
 */
export function validateFileForUpload(file: File): ClientValidation {
  if (file.size === 0) return { ok: false, reason: 'File is empty.' };
  if (file.size > MAX_IMAGE_BYTES) {
    return { ok: false, reason: `Larger than the ${Math.round(MAX_IMAGE_BYTES / 1024 / 1024)} MB limit.` };
  }
  // Client MIME is a hint only — the server sniffs the real format.
  if (file.type && !ACCEPTED_MIME_TYPES.includes(file.type as (typeof ACCEPTED_MIME_TYPES)[number])) {
    return { ok: false, reason: 'Unsupported type — use JPEG, PNG or WebP.' };
  }
  return { ok: true };
}

/** Default capture source for a plain file selection. */
export const DEFAULT_CAPTURE_SOURCE: CaptureSource = 'UPLOAD';
