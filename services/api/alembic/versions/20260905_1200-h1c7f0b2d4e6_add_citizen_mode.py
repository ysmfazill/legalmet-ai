"""citizen mode: anonymous scans + suspected-issue reports (UI-02)

Two new tables for the consumer-facing SCAN → DETECT → REVIEW → REPORT flow:

    citizen_scans   — one anonymous package scan: stored image, real usability
                      grade, real OCR + deterministic declaration extraction
                      results, and an automated SCREENING outcome (never a
                      legal determination — the outcome vocabulary cannot
                      express one).
    citizen_reports — a citizen-submitted suspected issue referencing a scan.
                      Status starts SUBMITTED; only department users advance
                      it. No inspection is auto-created.

Reversible via ``downgrade`` (drops both tables; report first, scan second,
respecting the FK).

Revision ID: h1c7f0b2d4e6
Revises: g9c5e3a1f7b2
Create Date: 2026-09-05 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h1c7f0b2d4e6"
down_revision: str | None = "g9c5e3a1f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "citizen_scans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("processed_storage_key", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("quality_grade", sa.String(length=16), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_status", sa.String(length=16), nullable=True),
        sa.Column(
            "quality_metrics",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("outcome_rationale", sa.Text(), nullable=True),
        sa.Column(
            "detected_fields",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "ocr_text",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("ocr_provider", sa.String(length=64), nullable=True),
        sa.Column("ocr_model", sa.String(length=64), nullable=True),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("reference", name="uq_citizen_scans_reference"),
    )
    op.create_index("ix_citizen_scans_reference", "citizen_scans", ["reference"])
    op.create_index("ix_citizen_scans_created_at", "citizen_scans", ["created_at"])

    op.create_table(
        "citizen_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column(
            "scan_id",
            sa.Uuid(),
            sa.ForeignKey(
                "citizen_scans.id",
                name="fk_citizen_reports_scan_id_citizen_scans",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SUBMITTED"),
        sa.Column("product", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("shop", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("issue", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reporter_name", sa.String(length=128), nullable=True),
        sa.Column("reporter_contact", sa.String(length=128), nullable=True),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("reference", name="uq_citizen_reports_reference"),
    )
    op.create_index("ix_citizen_reports_reference", "citizen_reports", ["reference"])
    op.create_index("ix_citizen_reports_created_at", "citizen_reports", ["created_at"])
    op.create_index("ix_citizen_reports_scan_id", "citizen_reports", ["scan_id"])
    op.create_index("ix_citizen_reports_status", "citizen_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_citizen_reports_status", table_name="citizen_reports")
    op.drop_index("ix_citizen_reports_scan_id", table_name="citizen_reports")
    op.drop_index("ix_citizen_reports_created_at", table_name="citizen_reports")
    op.drop_index("ix_citizen_reports_reference", table_name="citizen_reports")
    op.drop_table("citizen_reports")
    op.drop_index("ix_citizen_scans_created_at", table_name="citizen_scans")
    op.drop_index("ix_citizen_scans_reference", table_name="citizen_scans")
    op.drop_table("citizen_scans")
