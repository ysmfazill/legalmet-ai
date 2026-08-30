/**
 * Application-wide constants and identity for METRASIGHT.
 */

export const APP_NAME = 'METRASIGHT';

export const APP_TAGLINE = 'AI-Assisted Legal Metrology Inspection Intelligence';

export const PROBLEM_STATEMENT = {
  id: 'SIH26034',
  title:
    'Software System to check compliance of Packaged Commodities under Legal Metrology (Packaged Commodities) Rules, 2011 by scanning products, images and labels.',
  ministry: 'Ministry of Consumer Affairs, Food & Public Distribution',
  category: 'Software',
  theme: 'Agriculture, FoodTech & Rural Development',
} as const;

/**
 * The mandatory label placed on ANY fabricated / placeholder regulatory or
 * inspection data during the foundation phase. Do not remove.
 */
export const DEMO_DATA_LABEL = 'DEMO DATA — NOT LEGAL ADVICE';

export const DEMO_DATA_NOTICE =
  'This build uses clearly-labelled placeholder data. It does not contain verified Legal Metrology requirements and must not be used for real compliance decisions. Verified regulatory data will be added in a later phase from official sources.';

export const DEFAULT_PAGE_SIZE = 20;

/** Confidence thresholds used by the UI to colour/interpret model confidence. */
export const CONFIDENCE_THRESHOLDS = {
  high: 0.85,
  medium: 0.6,
} as const;
