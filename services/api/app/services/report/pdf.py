"""Report PDF renderer (UI-08 §14).

A REAL structured PDF built with reportlab platypus — never a screenshot and
never a fake. Input is the FROZEN ReportVersion snapshot (the only authority
for what an exported report claims).

Page structure (spec §14):
    1  header · inspection summary
    2  source complaint (when complaint-originated) · findings table
    3+ evidence images · evidence trace · regulatory basis · physical
       verification · lot intelligence · final decision · audit summary

Safety: no fake government letterhead, no official seals, no credentials.
All text passes through reportlab Paragraphs (escaped XML) — user-controlled
strings never become executable content.
"""
from __future__ import annotations

import io
import uuid
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.report.evidence_media import image_paragraphs

# Deep navy / light blue / white — the METRASIGHT palette (no seals, no gradients).
NAVY = colors.HexColor("#0F2A43")
LIGHT = colors.HexColor("#EAF1F7")
BORDER = colors.HexColor("#C6D3DE")
MUTED = colors.HexColor("#5A6B7A")
ORANGE = colors.HexColor("#B54708")

MAX_IMAGE_WIDTH_MM = 80
MAX_IMAGE_HEIGHT_MM = 60
MAX_IMAGES = 12  # exports note when the cap is hit — no silent truncation


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=16, textColor=NAVY, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "MSub", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=MUTED, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "MH2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, textColor=NAVY, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "MBody", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "MCell", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, leading=9.5, textColor=colors.black,
        ),
        "cellBold": ParagraphStyle(
            "MCellB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.5, leading=9.5, textColor=colors.black,
        ),
        "note": ParagraphStyle(
            "MNote", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=MUTED, spaceBefore=4, spaceAfter=4,
        ),
    }


def _kv_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    data = [
        [Paragraph(k, styles["cellBold"]), Paragraph(v or "—", styles["cell"])]
        for k, v in rows
    ]
    table = Table(data, colWidths=[45 * mm, 115 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _grid_table(header: list[str], rows: list[list[str]], styles: dict) -> Table:
    data = [[Paragraph(h, styles["cellBold"]) for h in header]]
    data += [[Paragraph(c or "—", styles["cell"]) for c in r] for r in rows]
    width = 160 * mm / max(len(header), 1)
    table = Table(data, colWidths=[width] * len(header), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _footer(canvas, doc) -> None:  # noqa: ANN001 — reportlab callback signature
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        18 * mm,
        12 * mm,
        "METRASIGHT — decision-support artifact. Not a government-issued "
        "document; no official seal.",
    )
    canvas.drawRightString(192 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _fmt(value: Any) -> str:
    """Stringify + XML-escape — every user-controlled string that reaches a
    reportlab Paragraph passes through here, so product names, observations
    and complaint text can never become PDF markup (spec §30)."""
    if value is None:
        return ""
    return xml_escape(str(value))


def render_report_pdf(
    snapshot: dict, *, evidence_items: list[dict], image_loader, audit_events: list[dict]
) -> bytes:
    """Build the official-style PDF.

    ``image_loader`` is a callable (evidence item detail) -> bytes | None
    provided by the router (it owns the storage service). Missing images are
    stated as "Evidence image unavailable." — never skipped silently.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"METRASIGHT Inspection Report {snapshot.get('inspectionReference', '')}",
        author="METRASIGHT",
    )
    styles = _styles()
    story: list[Any] = []
    inspection = snapshot.get("inspection") or {}
    complaint = snapshot.get("sourceComplaint")
    findings = snapshot.get("findings") or []
    measurements = snapshot.get("measurements") or []
    lots = snapshot.get("lots") or []
    decision = snapshot.get("decision")
    basis = snapshot.get("regulatoryBasis") or []
    completeness = snapshot.get("completeness") or {}

    # ---------------------------------------------------------- page 1: header
    story.append(Paragraph("METRASIGHT Inspection Report", styles["title"]))
    story.append(
        Paragraph(
            "AI-assisted Legal Metrology inspection — inspector-reviewed, "
            "evidence-backed decision-support artifact.",
            styles["subtitle"],
        )
    )
    story.append(
        _kv_table(
            [
                ("Report ID", str(snapshot.get("reportId", ""))[:36]),
                ("Inspection ID", str(snapshot.get("inspectionId", ""))[:36]),
                ("Inspection ref.", _fmt(inspection.get("reference"))),
                ("Report version", f"v{_fmt(snapshot.get('version', 1))}"),
                ("Result", _fmt(snapshot.get("result"))),
                ("Generated", _fmt(snapshot.get("generatedAt"))),
                ("Product", _fmt(inspection.get("productName"))),
                (
                    "Inspector",
                    _fmt(inspection.get("inspectorName")) or "NOT RECORDED",
                ),
                ("Inspection date", _fmt(inspection.get("date"))),
                ("Status", _fmt(inspection.get("status"))),
            ],
            styles,
        )
    )
    story.append(
        Paragraph(
            "Reports are decision-support artifacts generated from inspection "
            "evidence. They do not replace the authority of the authorized "
            "Legal Metrology inspector.",
            styles["note"],
        )
    )

    # --------------------------------------------- page 2: source + findings
    story.append(PageBreak())
    story.append(Paragraph("Source Context", styles["h2"]))
    if complaint:
        story.append(
            Paragraph(
                "This inspection originated from a citizen complaint. SOURCE "
                "evidence (submitted by the citizen) is reported separately "
                "from OFFICIAL inspection evidence and is never merged.",
                styles["note"],
            )
        )
        story.append(
            _kv_table(
                [
                    ("Complaint ref.", _fmt(complaint.get("reference"))),
                    ("Status", _fmt(complaint.get("status"))),
                    ("Product", _fmt(complaint.get("product"))),
                    ("Location", _fmt(complaint.get("location"))),
                    ("Issue", _fmt(complaint.get("issue"))),
                    ("Priority", _fmt(complaint.get("priority"))),
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph("Routine inspection — no citizen complaint origin.", styles["body"])
        )

    story.append(Paragraph("Executive Findings", styles["h2"]))
    if findings:
        story.append(
            _grid_table(
                ["ID", "Status", "Severity", "Requirement", "Rule", "Evidence", "Review"],
                [
                    [
                        f["id"][:8],
                        _fmt(f.get("status")),
                        _fmt(f.get("severity")),
                        _fmt(f.get("requirement"))[:90],
                        _fmt(f.get("ruleCode")),
                        _fmt(f.get("evidenceStatus")),
                        _fmt(f.get("reviewState")),
                    ]
                    for f in findings
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph("No evaluation findings recorded — NOT EVALUATED.", styles["body"])
        )

    # ------------------------------------------------- regulatory basis (§6)
    story.append(Paragraph("Regulatory Basis", styles["h2"]))
    for entry in basis:
        if entry.get("status") == "NOT_EVALUATED" or not entry.get("engineVersion"):
            story.append(
                Paragraph(
                    "NOT EVALUATED — REGULATORY REVIEW REQUIRED", styles["body"]
                )
            )
            continue
        story.append(
            _kv_table(
                [
                    ("Engine version", _fmt(entry.get("engineVersion"))),
                    ("Regulatory version", _fmt(entry.get("regulatoryVersionLabel"))),
                    ("Context date", _fmt(entry.get("contextDate"))),
                ],
                styles,
            )
        )
    story.append(
        Paragraph(
            "Regulatory basis is quoted from the deterministic engine output "
            "frozen at evaluation time. Unverified research-grade data is "
            "never presented as validated legal advice.",
            styles["note"],
        )
    )

    # ------------------------------------------------- physical verification
    story.append(Paragraph("Physical Verification", styles["h2"]))
    if measurements:
        story.append(
            _grid_table(
                [
                    "Declared",
                    "Measured",
                    "Observed diff.",
                    "Instrument",
                    "Recorded",
                    "Evaluation",
                ],
                [
                    [
                        _fmt(m.get("declaredValue")),
                        f"{_fmt(m.get('measuredValue'))} {_fmt(m.get('unit'))}".strip(),
                        _fmt(m.get("observedDifference")),
                        _fmt(m.get("instrumentId")) or "manual entry",
                        _fmt(m.get("recordedAt"))[:19],
                        _fmt((m.get("evaluation") or {}).get("status")),
                    ]
                    for m in measurements
                ],
                styles,
            )
        )
        story.append(
            Paragraph(
                "The observed difference is arithmetic on normalized values — "
                "a legal conclusion appears only from the frozen regulatory "
                "evaluation column, never from the difference itself.",
                styles["note"],
            )
        )
    else:
        story.append(Paragraph("No physical measurements recorded.", styles["body"]))

    # ------------------------------------------------------ lot intelligence
    if lots:
        story.append(Paragraph("Lot Intelligence", styles["h2"]))
        story.append(
            _grid_table(
                ["Lot", "Declared", "Lot size", "Sampled", "Measured", "Result"],
                [
                    [
                        _fmt(l.get("label")),
                        _fmt(l.get("declaredValue")),
                        _fmt(l.get("lotSize")),
                        _fmt(l.get("sampled")),
                        _fmt(l.get("measured")),
                        _fmt(l.get("decision")) or "IN PROGRESS",
                    ]
                    for l in lots
                ],
                styles,
            )
        )
        story.append(
            Paragraph(
                "Sampling shown is an AI-assisted inspection recommendation "
                "when no statutory sampling procedure applies — never a claim "
                "of the legally required sample.",
                styles["note"],
            )
        )

    # ------------------------------------------------------- evidence images
    story.append(PageBreak())
    story.append(Paragraph("Evidence", styles["h2"]))
    # UI-10 §24: the evidence_pack service returns snake_case keys
    # (evidence_type); accept the camelCase variant too so hand-built packs
    # keep working. Before this fix the filter matched nothing and evidence
    # images were silently dropped from every export.
    image_items = [
        i
        for i in evidence_items
        if (i.get("evidence_type") or i.get("evidenceType")) == "IMAGE"
    ]
    media = image_paragraphs(
        image_loader, image_items, max_items=MAX_IMAGES, styles_note=styles["note"]
    )
    story.extend(media)
    if len(image_items) > MAX_IMAGES:
        story.append(
            Paragraph(
                f"{len(image_items) - MAX_IMAGES} additional evidence images "
                "not embedded (export cap).",
                styles["note"],
            )
        )

    # Manifest summary — stable E-00N identifiers.
    story.append(Paragraph("Evidence Manifest", styles["h2"]))
    if evidence_items:
        story.append(
            _grid_table(
                ["Ref", "Type", "Label", "Origin"],
                [
                    [
                        _fmt(i.get("ref")),
                        _fmt(i.get("evidence_type") or i.get("evidenceType")),
                        _fmt(i.get("label"))[:80],
                        _fmt((i.get("detail") or {}).get("origin")),
                    ]
                    for i in evidence_items
                ],
                styles,
            )
        )
    else:
        story.append(Paragraph("No evidence manifest entries.", styles["body"]))

    # ------------------------------------------------------ inspector decision
    story.append(Paragraph("Inspector Decision", styles["h2"]))
    if decision:
        story.append(
            _kv_table(
                [
                    ("Decision", _fmt(decision.get("decision"))),
                    ("Reason", _fmt(decision.get("reason"))),
                    ("Decided by", _fmt(decision.get("decidedByName"))),
                    ("Decided at", _fmt(decision.get("decidedAt"))),
                ],
                styles,
            )
        )
    else:
        story.append(
            Paragraph(
                "NOT EVALUATED — no inspector decision recorded. The report "
                "cannot state a result without one.",
                styles["body"],
            )
        )
    story.append(
        Paragraph(
            "AI-assisted assessment. Final decision recorded by authorized "
            "inspector. The AI is never the final legal authority.",
            styles["note"],
        )
    )

    # ------------------------------------------------------------- audit trail
    story.append(Paragraph("Traceability", styles["h2"]))
    if audit_events:
        story.append(
            _grid_table(
                ["Event", "Role", "Actor", "At"],
                [
                    [
                        _fmt(e.get("eventType")),
                        _fmt(e.get("actorRole")),
                        _fmt(e.get("actorName")),
                        _fmt(e.get("createdAt"))[:19],
                    ]
                    for e in audit_events
                ],
                styles,
            )
        )
    story.append(
        Paragraph(
            f"Report version v{_fmt(snapshot.get('version', 1))} — snapshot "
            "frozen at generation time. Append-only audit trail preserved.",
            styles["note"],
        )
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
