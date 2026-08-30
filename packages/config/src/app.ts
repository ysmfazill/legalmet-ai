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
  'The regulatory dataset in this build is research-grade and UNVERIFIED against the official Gazette / India Code text, and aggregate pages use clearly-labelled demo data. Findings are decision support only and must not be used for real compliance decisions.';

/**
 * The role-of-the-system boundary shown wherever a reader might mistake
 * system output for a legal determination. Do not remove.
 */
export const SYSTEM_ROLE_NOTICE =
  'METRASIGHT provides AI-assisted inspection intelligence and evidence organization. Final regulatory determination remains with the authorized inspector.';

export const DEFAULT_PAGE_SIZE = 20;

/** Confidence thresholds used by the UI to colour/interpret model confidence. */
export const CONFIDENCE_THRESHOLDS = {
  high: 0.85,
  medium: 0.6,
} as const;
