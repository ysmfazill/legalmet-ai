"""reports, report versions and evidence manifest (UI-08)

New tables:

* ``reports`` — one live report record per inspection pointing at the current
  version. Lifecycle DRAFT → UNDER_REVIEW → FINALIZED → EXPORTED (AMENDED when
  a new version supersedes a finalized one). The result column carries the
  inspector's recorded decision or NOT_EVALUATED — never a report-side
  invention.
* ``report_versions`` — one immutable snapshot JSON per generation. Everything
  the report asserts is frozen at generation time so later data changes can
  never rewrite what an exported report claimed. Previous finalized versions
  are preserved verbatim (never silently overwritten).
* ``report_evidence`` — the ordered evidence manifest of one version with
  stable E-00N identifiers, referencing EXISTING records by id. Nothing is
  copied — provenance is preserved by reference.

Reversible via ``downgrade``.

Revision ID: n8a1c3e5f7b2
Revises: m7b2d9e4f6a1
Create Date: 2026-09-06 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n8a1c3e5f7b2"
down_revision: str | None = "m7b2d9e4f6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "inspection_id",
            sa.Uuid(),
            sa.ForeignKey(
                "inspections.id",
                name="fk_reports_inspection_id_inspections",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_reports_created_by_users", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "finalized_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_reports_finalized_by_users", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amendment_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_reports_inspection_id", "reports", ["inspection_id"], unique=True)
    op.create_index("ix_reports_status", "reports", ["status"])

    op.create_table(
        "report_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey(
                "reports.id",
                name="fk_report_versions_report_id_reports",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id", name="fk_report_versions_created_by_users", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_report_versions_report_id", "report_versions", ["report_id"])
    op.create_index(
        "ix_report_versions_version",
        "report_versions",
        ["report_id", "version"],
        unique=True,
    )

    op.create_table(
        "report_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "report_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "report_versions.id",
                name="fk_report_evidence_report_version_id_report_versions",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_report_evidence_report_version_id",
        "report_evidence",
        ["report_version_id"],
    )
    op.create_index("ix_report_evidence_sequence", "report_evidence", ["sequence"])


def downgrade() -> None:
    op.drop_index("ix_report_evidence_sequence", table_name="report_evidence")
    op.drop_index("ix_report_evidence_report_version_id", table_name="report_evidence")
    op.drop_table("report_evidence")

    op.drop_index("ix_report_versions_version", table_name="report_versions")
    op.drop_index("ix_report_versions_report_id", table_name="report_versions")
    op.drop_table("report_versions")

    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_inspection_id", table_name="reports")
    op.drop_table("reports")
