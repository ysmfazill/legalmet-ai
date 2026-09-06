"""Evidence image handling shared by the PDF and DOCX renderers (UI-08 §11/§31).

Originals are preserved verbatim in storage; exports embed an OPTIMIZED
derivative (downscaled via Pillow) so large evidence packs do not bloat the
file. A missing image is stated as "Evidence image unavailable." — never
fabricated, never silently skipped.
"""
from __future__ import annotations

import io
from typing import Any, Callable

from PIL import Image as PILImage

MAX_EMBED_WIDTH = 800
MAX_EMBED_HEIGHT = 600


def optimize_image_bytes(data: bytes, *, mime_hint: str | None = None) -> bytes | None:
    """Downscale to the embed budget and re-encode (PNG for alpha, JPEG else).

    Returns None when the bytes are not a decodable image — a fact the caller
    reports, never a placeholder graphic.
    """
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            img.load()
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB" if mime_hint == "image/jpeg" else "RGBA")
            img.thumbnail((MAX_EMBED_WIDTH, MAX_EMBED_HEIGHT))
            out = io.BytesIO()
            if img.mode == "RGBA":
                img.save(out, format="PNG")
            else:
                img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception:  # noqa: BLE001 — undecodable bytes are "unavailable"
        return None


def image_paragraphs(
    image_loader: Callable[[dict | None], bytes | None],
    image_items: list[dict],
    *,
    max_items: int,
    styles_note: Any,
) -> list[Any]:
    """reportlab flowables for the evidence images, each with its E-ref label.

    ``image_loader(item.detail) -> bytes | None`` is provided by the router
    (it owns the storage service).
    """
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import KeepTogether, Paragraph, Spacer

    flow: list[Any] = []
    for item in image_items[:max_items]:
        detail = item.get("detail") or {}
        raw = image_loader(detail)
        optimized = optimize_image_bytes(raw) if raw else None
        if optimized is None:
            flow.append(
                Paragraph(
                    f"{item.get('ref', '')} — Evidence image unavailable.",
                    styles_note,
                )
            )
            continue
        buf = io.BytesIO(optimized)
        with PILImage.open(buf) as img:
            w_px, h_px = img.size
        # 72 dpi: px → pt directly; cap inside the embed budget.
        scale = min(
            1.0,
            (MAX_EMBED_WIDTH * 0.9) / max(w_px, 1),
            (MAX_EMBED_HEIGHT * 0.9) / max(h_px, 1),
        )
        flow.append(
            KeepTogether(
                [
                    Paragraph(
                        f"{item.get('ref', '')} — {_safe_caption(item)}",
                        styles_note,
                    ),
                    RLImage(
                        buf,
                        width=w_px * scale,
                        height=h_px * scale,
                    ),
                    Spacer(1, 6),
                ]
            )
        )
    return flow


def _safe_caption(item: dict) -> str:
    detail = item.get("detail") or {}
    # Filenames are user-controlled — escape so they can never become PDF
    # markup (spec §30).
    caption = f"Evidence image {_fmt_ref(detail.get('filename'))}"
    from xml.sax.saxutils import escape as xml_escape

    return xml_escape(caption)


def _fmt_ref(value: Any) -> str:
    return str(value) if value else ""
