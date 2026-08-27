import { useCallback, useState } from 'react';

import type { Inspection, PackageImage } from '@legalmet/types';

import { api, ApiClientError } from '../api/client';

export type IntakePhase = 'collect' | 'created' | 'finalized';

export interface IntakeSession {
  inspectionId: string | null;
  inspection: Inspection | null;
  phase: IntakePhase;
  images: PackageImage[];
  creating: boolean;
  finalizing: boolean;
  /** id of the image currently being mutated (remove/prepare). */
  busyImageId: string | null;
  error: string | null;

  create: (details: { productName: string; productCategory: string; note?: string }) => Promise<Inspection | null>;
  addImage: (image: PackageImage) => void;
  removeImage: (image: PackageImage) => Promise<void>;
  prepareImage: (image: PackageImage) => Promise<void>;
  finalize: () => Promise<Inspection | null>;
  clearError: () => void;
}

function messageOf(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  return error instanceof Error ? error.message : 'Something went wrong.';
}

/**
 * Owns the durable state of one real intake session — the created inspection
 * and its stored images — and wraps the authenticated API calls. Transient UI
 * (file selection, upload progress) lives in the panels that drive it.
 *
 * Nothing here runs OCR, vision or compliance logic. `finalize()` reaches the
 * strongest possible intake outcome: READY_FOR_ANALYSIS.
 */
export function useIntakeSession(): IntakeSession {
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [images, setImages] = useState<PackageImage[]>([]);
  const [phase, setPhase] = useState<IntakePhase>('collect');
  const [creating, setCreating] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [busyImageId, setBusyImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback<IntakeSession['create']>(async (details) => {
    setCreating(true);
    setError(null);
    try {
      const created = await api.createInspection(details);
      setInspection(created);
      setPhase('created');
      return created;
    } catch (err) {
      setError(messageOf(err));
      return null;
    } finally {
      setCreating(false);
    }
  }, []);

  const addImage = useCallback((image: PackageImage) => {
    setImages((prev) => (prev.some((i) => i.id === image.id) ? prev : [...prev, image]));
  }, []);

  const removeImage = useCallback<IntakeSession['removeImage']>(async (image) => {
    setBusyImageId(image.id);
    setError(null);
    try {
      await api.deleteImage(image.id);
      setImages((prev) => prev.filter((i) => i.id !== image.id));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusyImageId(null);
    }
  }, []);

  const prepareImage = useCallback<IntakeSession['prepareImage']>(async (image) => {
    setBusyImageId(image.id);
    setError(null);
    try {
      const updated = await api.prepareImage(image.id);
      setImages((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusyImageId(null);
    }
  }, []);

  const finalize = useCallback<IntakeSession['finalize']>(async () => {
    if (!inspection) return null;
    setFinalizing(true);
    setError(null);
    try {
      const ready = await api.markReady(inspection.id);
      setInspection(ready);
      setPhase('finalized');
      return ready;
    } catch (err) {
      setError(messageOf(err));
      return null;
    } finally {
      setFinalizing(false);
    }
  }, [inspection]);

  const clearError = useCallback(() => setError(null), []);

  return {
    inspectionId: inspection?.id ?? null,
    inspection,
    phase,
    images,
    creating,
    finalizing,
    busyImageId,
    error,
    create,
    addImage,
    removeImage,
    prepareImage,
    finalize,
    clearError,
  };
}
