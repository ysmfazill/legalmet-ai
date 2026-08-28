"""Real perception pipeline (Prompt 4).

Turns a REAL stored package image into traceable, structured perception
output — OCR text with boxes and confidence, visual regions, and deterministic
declaration candidates — each linked into the evidence chain:

    IMAGE -> REGION -> OCR -> FIELD

Strict scope: this package is perception only. It never evaluates regulatory
requirements and never produces a compliance conclusion. The strongest claim it
makes about any field is DETECTED / REVIEW_REQUIRED / NOT_EXTRACTED.
"""
