"""OCR text normalization (derived — raw text is never overwritten).

Conservative, deterministic tidy-up applied to raw OCR output so downstream
extraction sees common shapes. Everything here is a pure function of the raw
string; the raw value remains the immutable evidence.
"""
from __future__ import annotations

import re
import unicodedata

# Collapse runs of whitespace (including OCR line breaks) to single spaces.
_WHITESPACE_RE = re.compile(r"\s+")
# No space directly after a currency token: "MRP ₹ 499" -> "MRP ₹499",
# "Rs . 199" -> "Rs. 199".
_CURRENCY_SPACE_RE = re.compile(r"(₹|Rs\.?|INR)\s+", re.IGNORECASE)
# Common OCR confusions inside numbers only (never inside words): "1O0" -> "100".
_NUM_TOKEN_RE = re.compile(r"\b[\dOoIl.,]+\b")


def normalize_ocr_text(raw: str) -> str:
    """Derive the normalized form of one raw OCR line."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFC", raw)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = _CURRENCY_SPACE_RE.sub(lambda m: m.group(1) if m.group(1) != "INR" else "INR ", text)
    text = _fix_numberish_tokens(text)
    return text


def _fix_numberish_tokens(text: str) -> str:
    """Repair letter/digit confusions, but only inside number-like tokens."""
    def _fix(match: re.Match[str]) -> str:
        token = match.group(0)
        # Leave pure punctuation separators alone.
        if not any(ch.isdigit() for ch in token):
            return token
        fixed = token.replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1")
        return fixed

    return _NUM_TOKEN_RE.sub(_fix, text)
