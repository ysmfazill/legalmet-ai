"""Generate the local packaged-commodity TEST DATASET (Prompt 9, Phase 2).

Renders SYNTHETIC package-label images with Pillow — every image is generated
locally from strings defined in this file. No copyrighted or third-party
material is used, so the rendered PNGs are safe to commit.

Output
------
* ``images/*.png``  — the rendered labels (committed: deterministic content).
* ``manifest.json`` — one record per image: id, category, language, condition,
  the exact rendered label lines, and the EXPECTED perception behaviour.

Honesty rules for the manifest (no fabricated accuracy claims)
--------------------------------------------------------------
* ``expected_fields`` lists only fields whose values are printed verbatim on
  the synthetic label — it says what the label CONTAINS, not what OCR will
  read. Recognition quality is condition-dependent and is NOT claimed as an
  accuracy percentage.
* The bilingual image mixes simple Devanagari lines (rendered WITHOUT complex
  text shaping — Pillow lacks raqm here) with English lines. Under the current
  English-only OCR configuration the Hindi lines are expected to be missed;
  the manifest records that expectation instead of claiming Hindi support.
* Degraded-condition images record RELATIVE expectations (e.g. "fields missed
  or flagged REVIEW_REQUIRED"), never hard guarantees.

Run from ``services/api``:
    .venv/Scripts/python.exe tests/dataset/generate.py
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
IMAGES_DIR = HERE / "images"
MANIFEST_PATH = HERE / "manifest.json"

# Fonts: a real TrueType face for label-like rendering. Devanagari uses the
# Windows Nirmala UI collection when present (no complex shaping without raqm).
_ENGLISH_FONT = "arial.ttf"
_DEVANAGARI_FONT = r"C:\Windows\Fonts\Nirmala.ttc"


def _font(size: int, devanagari: bool = False) -> ImageFont.FreeTypeFont:
    name = _DEVANAGARI_FONT if devanagari else _ENGLISH_FONT
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Base label definitions — synthetic brands only (no real trademarks).
# Every string below is exactly what gets rendered onto the pixels.
# ---------------------------------------------------------------------------

def _food_label() -> list[tuple[str, int, bool]]:
    """Packaged-food front+info label: (text, font-size, is-devanagari)."""
    return [
        ("SUNRISE CRUNCHY MASALA", 58, False),
        ("Net Qty: 250 g", 38, False),
        ("M.R.P. Rs. 149.00 (inclusive of all taxes)", 38, False),
        ("Batch No: SM-2481", 34, False),
        ("Mfg. Date: 03/2026", 34, False),
        ("Country of Origin: India", 34, False),
        ("Consumer Care: care@sunrise.example", 30, False),
        ("Best Before 6 months from packaging", 30, False),
    ]


def _water_label() -> list[tuple[str, int, bool]]:
    return [
        ("AQUAPURE PACKAGED DRINKING WATER", 52, False),
        ("Net Quantity: 1 L", 40, False),
        ("M.R.P. Rs. 20.00", 38, False),
        ("Batch No: AQ-77120", 34, False),
        ("Mfg. Date: 07/2026", 34, False),
        ("Best Before: 6 months", 32, False),
        ("Packaged by: AQUAPURE Beverages, Kochi, Kerala", 28, False),
    ]


def _oil_label() -> list[tuple[str, int, bool]]:
    return [
        ("GOLDLEAF SUNFLOWER OIL", 56, False),
        ("Net Quantity: 1 L", 40, False),
        ("M.R.P. Rs. 165.00 (inclusive of all taxes)", 36, False),
        ("Batch No: GL-40516", 34, False),
        ("Mfg. Date: 05/2026", 34, False),
        ("Country of Origin: India", 32, False),
        ("Packed by: GOLDLEAF Foods Pvt Ltd, Chennai", 28, False),
    ]


def _snacks_label() -> list[tuple[str, int, bool]]:
    return [
        ("CRISPYBITES CHIPS", 56, False),
        ("Net Qty: 52 g", 38, False),
        ("M.R.P. Rs. 10.00", 36, False),
        ("Batch No: CB-99012", 34, False),
        ("Best Before: 4 months", 32, False),
        ("Manufactured by: CRISPYBITES Snacks, Indore", 28, False),
    ]


def _household_label() -> list[tuple[str, int, bool]]:
    return [
        ("SPARKLEWASH DETERGENT POWDER", 48, False),
        ("Net Quantity: 500 g", 38, False),
        ("M.R.P. Rs. 65.00 (inclusive of all taxes)", 34, False),
        ("Batch No: SW-33081", 32, False),
        ("Mfg. Date: 02/2026", 32, False),
        ("Country of Origin: India", 30, False),
        ("Consumer Care: 1800-222-345", 28, False),
    ]


def _cosmetic_label() -> list[tuple[str, int, bool]]:
    return [
        ("PETALFRESH FACE WASH", 52, False),
        ("Net Quantity: 100 ml", 38, False),
        ("M.R.P. Rs. 199.00", 36, False),
        ("Batch No: PF-20461", 34, False),
        ("Mfg. Date: 01/2026", 34, False),
        ("Best Before 24 months", 30, False),
        ("Address: PETALFRESH Care Ltd, Mumbai 400001", 26, False),
    ]


def _dense_food_label() -> list[tuple[str, int, bool]]:
    rows = _food_label()
    extra = [
        ("Ingredients: Wheat Flour, Palm Oil, Salt, Spices, Masala Mix", 22, False),
        ("Nutrition per 100g: Energy 512 kcal, Protein 6.4 g, Fat 27.1 g,", 20, False),
        ("Carbohydrate 61.8 g, Sugars 3.2 g, Sodium 0.6 g", 20, False),
        ("Storage: Store in a cool dry place away from direct sunlight", 22, False),
        ("Contains added preservatives (INS 211)", 22, False),
        ("Manufactured by: SUNRISE Foods Pvt Ltd, Bengaluru 560001", 22, False),
        ("FSSAI Lic. No. 10012345678901", 22, False),
        ("Customer care: care@sunrise.example / 1800-111-222", 22, False),
    ]
    return rows + extra


def _bilingual_label() -> list[tuple[str, int, bool]]:
    """English + simple Devanagari lines (no conjuncts; shaping-free render)."""
    return [
        ("HIMALAY AATA / FLOUR", 50, False),
        ("Net Qty: 5 kg", 38, False),
        ("M.R.P. Rs. 245.00", 36, False),
        ("देश का उत्पाद: भारत", 34, True),  # rendered without complex shaping
        ("Batch No: HA-11223", 32, False),
        ("Mfg. Date: 06/2026", 32, False),
    ]


def _multiblock_layout() -> list[list[tuple[str, int, bool]]]:
    """Two side-by-side panels (front + info) — multiple text blocks."""
    front = [
        ("TWINPANEL RICE BASMATI", 40, False),
        ("Premium Grade", 26, False),
        ("Net Qty: 1 kg", 32, False),
    ]
    info = [
        ("M.R.P. Rs. 128.00", 28, False),
        ("Batch No: TP-50617", 26, False),
        ("Mfg. Date: 04/2026", 26, False),
        ("Origin: India", 26, False),
        ("Packer: TWINPANEL Foods, Delhi", 22, False),
    ]
    return [front, info]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

MARGIN = 60
LINE_GAP = 26


def _render_plain(lines: list[tuple[str, int, bool]], width: int = 1000) -> Image.Image:
    height = MARGIN * 2 + sum(size + LINE_GAP for _, size, _ in lines)
    img = Image.new("RGB", (width, height), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline=(0, 0, 0), width=6)
    y = MARGIN
    for text, size, deva in lines:
        draw.text((MARGIN, y), text, fill=(12, 12, 12), font=_font(size, deva))
        y += size + LINE_GAP
    return img


def _render_multiblock(blocks: list[list[tuple[str, int, bool]]], width: int = 1200) -> Image.Image:
    heights = [
        MARGIN * 2 + sum(size + LINE_GAP for _, size, _ in block) for block in blocks
    ]
    height = max(heights) + 40
    img = Image.new("RGB", (width, height), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline=(0, 0, 0), width=6)
    panel_w = (width - MARGIN * 3) // len(blocks)
    for index, block in enumerate(blocks):
        x = MARGIN + index * (panel_w + MARGIN)
        if index:
            divider = x - MARGIN // 2
            draw.line([divider, 50, divider, height - 50], fill=(120, 120, 120), width=3)
        y = MARGIN
        for text, size, deva in block:
            draw.text((x, y), text, fill=(12, 12, 12), font=_font(size, deva))
            y += size + LINE_GAP
    return img


# --- condition transforms (perceptual degradations, all reversible in code) ---

def _low_light(img: Image.Image) -> Image.Image:
    return ImageEnhance.Brightness(img).enhance(0.45)


def _glare(img: Image.Image) -> Image.Image:
    """Two bright diagonal streaks across the label."""
    overlay = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(overlay)
    w, h = img.size
    for start in (int(h * 0.25), int(h * 0.55)):
        band = [
            (0, start),
            (w, start - int(h * 0.08)),
            (w, start + int(h * 0.05)),
            (0, start + int(h * 0.03)),
        ]
        d.polygon(band, fill=110)
    white = Image.new("RGB", img.size, (255, 255, 255))
    return Image.composite(white, img, overlay)


def _rotate(img: Image.Image, degrees: float = 10.0) -> Image.Image:
    return img.rotate(degrees, expand=True, fillcolor=(248, 248, 248), resample=Image.BICUBIC)


def _perspective(img: Image.Image) -> Image.Image:
    """Quad warp: the label plane seen off-angle (keystoning)."""
    w, h = img.size
    quad = {
        (0, 0): (int(w * 0.10), int(h * 0.06)),
        (w, 0): (int(w * 0.94), int(h * 0.12)),
        (w, h): (int(w * 0.88), h),
        (0, h): (int(w * 0.06), int(h * 0.96)),
    }
    identity = {(0, 0): (0, 0), (w, 0): (w, 0), (w, h): (w, h), (0, h): (0, h)}
    coeffs = _find_coeffs(quad, identity)
    return img.transform(
        (w, h), Image.PERSPECTIVE, coeffs, resample=Image.BICUBIC, fillcolor=(248, 248, 248)
    )


def _find_coeffs(pa, pb) -> list[float]:
    """Solve the perspective transform matrix mapping pb -> pa (Pillow recipe)."""
    matrix = []
    for (x, y), (X, Y) in zip(pb.values(), pa.values(), strict=True):
        matrix.append([X, Y, 1, 0, 0, 0, -x * X, -x * Y])
        matrix.append([0, 0, 0, X, Y, 1, -y * X, -y * Y])
    import numpy as np

    A = np.array(matrix, dtype=float)
    B = np.array([c for (x, y) in pb for c in (x, y)], dtype=float)
    res = np.linalg.solve(A, B)
    return [float(v) for v in res]


def _curved(img: Image.Image) -> Image.Image:
    """Cylindrical warp — label wrapped around a round package body."""
    import numpy as np

    w, h = img.size
    arr = np.asarray(img)
    xs = np.arange(w)
    shift = (np.sin((xs / w) * np.pi) * (w * 0.06)).astype(int)  # bulge
    out = np.full_like(arr, 248)
    for x in range(w):
        dx = shift[x]
        out[:, max(0, x - dx): min(w, x - dx + 1)] = arr[:, x: x + 1]
    return Image.fromarray(out)


def _obstruct(img: Image.Image) -> Image.Image:
    """A thumb/finger occluding the MRP region."""
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.ellipse([w * 0.45, h * 0.30, w * 0.95, h * 0.42], fill=(96, 74, 60))
    return img


def _small_text(lines: list[tuple[str, int, bool]]) -> list[tuple[str, int, bool]]:
    return [(text, max(16, size // 2), deva) for text, size, deva in lines]


def _blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(2.2))


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------

def build_dataset() -> list[dict]:
    """Render every dataset image and return its manifest records."""
    records: list[dict] = []

    def emit(
        record_id: str,
        category: str,
        language: str,
        condition: str,
        img: Image.Image,
        label_lines: list[str],
        expected_fields: dict[str, str],
        expected_extraction: str,
        expected_review: str,
    ) -> None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        path = IMAGES_DIR / f"{record_id.lower()}.png"
        path.write_bytes(_to_png_bytes(img))
        records.append(
            {
                "id": record_id,
                "file": f"images/{path.name}",
                "category": category,
                "language": language,
                "condition": condition,
                "pixelSize": f"{img.width}x{img.height}",
                "labelLines": label_lines,  # exact strings rendered on pixels
                "expectedVisibleFields": expected_fields,
                "expectedExtraction": expected_extraction,
                "expectedReview": expected_review,
            }
        )

    def lines_of(rows: list[tuple[str, int, bool]]) -> list[str]:
        return [text for text, _, _ in rows]

    # --- one clean label per category ---------------------------------------
    food = _food_label()
    emit(
        "FOOD-CLEAN-001", "packaged-food", "en", "clean-front-label",
        _render_plain(food), lines_of(food),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00", "batch_number": "SM-2481",
         "date_of_manufacture": "03/2026", "country_of_origin": "India",
         "consumer_care": "care@sunrise.example"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / DATE_OF_MANUFACTURE / COUNTRY_OF_ORIGIN"
        " / CONSUMER_CARE candidates expected",
        "clean render: no perception review expected",
    )
    water = _water_label()
    emit(
        "WATER-CLEAN-001", "drinking-water", "en", "clean-front-label",
        _render_plain(water), lines_of(water),
        {"net_quantity": "1 L", "mrp": "Rs. 20.00", "batch_number": "AQ-77120"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / DATE_OF_MANUFACTURE / BEST_BEFORE"
        " candidates expected",
        "clean render: no perception review expected",
    )
    oil = _oil_label()
    emit(
        "OIL-CLEAN-001", "edible-oil", "en", "clean-front-label",
        _render_plain(oil), lines_of(oil),
        {"net_quantity": "1 L", "mrp": "Rs. 165.00", "batch_number": "GL-40516"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / DATE_OF_MANUFACTURE / COUNTRY_OF_ORIGIN"
        " candidates expected",
        "clean render: no perception review expected",
    )
    snacks = _snacks_label()
    emit(
        "SNACKS-CLEAN-001", "snacks", "en", "clean-front-label",
        _render_plain(snacks), lines_of(snacks),
        {"net_quantity": "52 g", "mrp": "Rs. 10.00", "batch_number": "CB-99012"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / BEST_BEFORE candidates expected",
        "clean render: no perception review expected",
    )
    household = _household_label()
    emit(
        "HOUSEHOLD-CLEAN-001", "household-goods", "en", "clean-front-label",
        _render_plain(household), lines_of(household),
        {"net_quantity": "500 g", "mrp": "Rs. 65.00", "batch_number": "SW-33081"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / DATE_OF_MANUFACTURE / COUNTRY_OF_ORIGIN"
        " candidates expected",
        "clean render: no perception review expected",
    )
    cosmetic = _cosmetic_label()
    emit(
        "COSMETIC-CLEAN-001", "cosmetic-personal-care", "en", "clean-front-label",
        _render_plain(cosmetic), lines_of(cosmetic),
        {"net_quantity": "100 ml", "mrp": "Rs. 199.00", "batch_number": "PF-20461"},
        "MRP / NET_QUANTITY / BATCH_NUMBER / DATE_OF_MANUFACTURE / BEST_BEFORE"
        " candidates expected",
        "clean render: no perception review expected",
    )

    # --- condition variants on the packaged-food base ------------------------
    emit(
        "FOOD-LOWLIGHT-002", "packaged-food", "en", "low-lighting",
        _low_light(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00"},
        "diminished contrast: some candidates missed or flagged REVIEW_REQUIRED"
        " (relative expectation, no accuracy claim)",
        "REVIEW_REQUIRED possible; image quality grade may drop to POOR",
    )
    emit(
        "FOOD-GLARE-003", "packaged-food", "en", "glare",
        _glare(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00"},
        "glare streaks may obscure MRP lines: missed or low-confidence candidates expected",
        "REVIEW_REQUIRED possible for obscured lines",
    )
    emit(
        "FOOD-ROTATED-004", "packaged-food", "en", "rotation",
        _rotate(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00"},
        "10-degree rotation: most English lines still expected; degrades with angle",
        "possible partial misses; not guaranteed",
    )
    emit(
        "FOOD-PERSPECTIVE-005", "packaged-food", "en", "perspective-distortion",
        _perspective(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00"},
        "keystoned plane: variable recognition, no accuracy claim",
        "REVIEW_REQUIRED possible",
    )
    small = _small_text(food)
    emit(
        "FOOD-SMALLTEXT-006", "packaged-food", "en", "small-text",
        _render_plain(small, width=800), lines_of(small),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00"},
        "half-size fonts: recognition is materially harder; expect missed / low-confidence lines",
        "REVIEW_REQUIRED expected for some fields",
    )
    blocks = _multiblock_layout()
    emit(
        "FOOD-MULTIBLOCK-007", "packaged-food", "en", "multiple-text-blocks",
        _render_multiblock(blocks), [line for block in blocks for line in lines_of(block)],
        {"net_quantity": "1 kg", "mrp": "Rs. 128.00", "batch_number": "TP-50617"},
        "two side-by-side panels: candidates from both blocks expected",
        "no review expected on a clean render",
    )
    dense = _dense_food_label()
    emit(
        "FOOD-DENSE-008", "packaged-food", "en", "dense-label",
        _render_plain(dense), lines_of(dense),
        {"net_quantity": "250 g", "mrp": "Rs. 149.00", "batch_number": "SM-2481"},
        "many packed lines incl. ingredients/nutrition: core fields expected,"
        " noise lines tolerated",
        "no review expected on a clean render",
    )
    emit(
        "FOOD-OBSTRUCTED-009", "packaged-food", "en", "partial-obstruction",
        _obstruct(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g", "batch_number": "SM-2481"},
        "the MRP line is physically occluded: MRP expected missed or NOT_EXTRACTED;"
        " other fields intact",
        "obstructed field expected REVIEW_REQUIRED / NOT_EXTRACTED",
    )
    emit(
        "FOOD-CURVED-010", "packaged-food", "en", "curved-package",
        _curved(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g"},
        "cylindrical warp distorts horizontal baselines: variable recognition",
        "REVIEW_REQUIRED possible",
    )
    emit(
        "FOOD-BLUR-011", "packaged-food", "en", "motion-blur",
        _blur(_render_plain(food)), lines_of(food),
        {"net_quantity": "250 g"},
        "gaussian blur: expect degraded recognition and lower confidence",
        "REVIEW_REQUIRED expected; quality grade may drop to POOR",
    )
    bilingual = _bilingual_label()
    emit(
        "FOOD-BILINGUAL-012", "packaged-food", "en+hi", "bilingual-label",
        _render_plain(bilingual), lines_of(bilingual),
        {"net_quantity": "5 kg", "mrp": "Rs. 245.00", "batch_number": "HA-11223"},
        "English lines extractable; Devanagari lines are NOT supported by the current"
        " English-only OCR configuration (rendered without complex shaping) —"
        " expected to be missed",
        "Hindi-origin lines are unsupported-language behaviour, not an accuracy claim",
    )

    # --- quality-gate extremes (perception quality only, never a legal verdict) ---
    tiny = _render_plain(_small_text(food), width=220).resize((110, 160))
    emit(
        "FOOD-TINYRES-013", "packaged-food", "en", "extreme-low-resolution",
        tiny, lines_of(food),
        {},
        "110x160 px: expected to be REJECTED or POOR by the image-quality gate before OCR",
        "quality-gate rejection expected (perception-quality signal only)",
    )
    emit(
        "FOOD-EXTREMEDARK-014", "packaged-food", "en", "extreme-darkness",
        ImageEnhance.Brightness(_render_plain(food)).enhance(0.15), lines_of(food),
        {},
        "15% brightness: expected to grade POOR/REJECTED by the quality gate; OCR likely unusable",
        "quality-gate rejection or REVIEW_REQUIRED expected",
    )

    return records


def main() -> None:
    records = build_dataset()
    manifest = {
        "name": "METRASIGHT packaged-commodity test dataset",
        "version": "1.0",
        "origin": (
            "All images are locally rendered synthetic labels (Pillow) —"
            " no copyrighted or third-party material."
        ),
        "accuracyDisclaimer": (
            "expected fields describe what is printed on the synthetic label,"
            " not measured OCR accuracy. No accuracy percentage is claimed"
            " for any condition."
        ),
        "usage": "integration tests + image-quality gate tests + manual demo walkthrough",
        "images": records,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(records)} images to {IMAGES_DIR}")
    print(f"wrote manifest {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
