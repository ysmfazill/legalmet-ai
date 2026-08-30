"""add human-in-the-loop review tables (Prompt 8)

Creates the HITL tables:

    field_corrections:      one inspector correction of one extracted field —
                            append-only before/after history; the ORIGINAL
                            OCR/AI values on extracted_fields are never
                            touched
    finding_reviews:        the human review state of ONE engine finding
                            (unique per finding), backend-enforced state
                            machine
    finding_review_events:  append-only transition history of each review
    inspection_decisions:   the FINAL human decision on an inspection —
                            supersede-only history (never overwritten,
                            never deleted)

Also adds corrected_by / corrected_reason columns to extracted_fields so the
latest correction's actor is resolvable without a join (the correction history
itself remains in field_corrections, untouched).

The change is purely additive (three new tables + two nullable columns); no
existing table's semantics change, so it is safe on a populated database.
Reversible via ``downgrade`` (drop the tables / columns).

Revision ID: f8b2d6a4c1e9
Revises: e7a4c1f8b3d2
Create Date: 2026-08-30 09:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b2d6a4c1e9"
down_revision: str | None = "e7a4c1f8b3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # --- latest-correction actor columns on extracted_fields -----------------
    with op.batch_alter_table("extracted_fields") as batch:
        batch.add_column(sa.Column("corrected_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("corrected_reason", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_extracted_fields_corrected_by"), "extracted_fields", ["corrected_by"]
    )

    # --- field correction history ---------------------------------------------
    op.create_table(
        "field_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("extracted_field_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_by", sa.Uuid(), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("previous_raw_text", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triggered_by_evaluation_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_corrections")),
        sa.ForeignKeyConstraint(
            ["extracted_field_id"],
            ["extracted_fields.id"],
            name=op.f("fk_field_corrections_extracted_field_id_extracted_fields"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_field_corrections_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_by"],
            ["users.id"],
            name=op.f("fk_field_corrections_corrected_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_evaluation_id"],
            ["compliance_evaluations.id"],
            name=op.f(
                "fk_field_corrections_triggered_by_evaluation_id_compliance_evaluations"
            ),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_field_corrections_extracted_field_id"),
        "field_corrections",
        ["extracted_field_id"],
    )
    op.create_index(
        op.f("ix_field_corrections_inspection_id"), "field_corrections", ["inspection_id"]
    )
    op.create_index(
        op.f("ix_field_corrections_corrected_by"), "field_corrections", ["corrected_by"]
    )

    # --- finding review state + history ----------------------------------------
    op.create_table(
        "finding_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correction_id", sa.Uuid(), nullable=True),
        sa.Column("escalated_to_role", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_reviews")),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["evaluation_findings.id"],
            name=op.f("fk_finding_reviews_finding_id_evaluation_findings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_finding_reviews_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_finding_reviews_reviewed_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["correction_id"],
            ["field_corrections.id"],
            name=op.f("fk_finding_reviews_correction_id_field_corrections"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("finding_id", name="uq_finding_reviews_finding_id"),
    )
    op.create_index(op.f("ix_finding_reviews_finding_id"), "finding_reviews", ["finding_id"])
    op.create_index(
        op.f("ix_finding_reviews_inspection_id"), "finding_reviews", ["inspection_id"]
    )
    op.create_index(op.f("ix_finding_reviews_state"), "finding_reviews", ["state"])
    op.create_index(
        op.f("ix_finding_reviews_reviewed_by"), "finding_reviews", ["reviewed_by"]
    )

    op.create_table(
        "finding_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("previous_state", sa.String(length=32), nullable=True),
        sa.Column("new_state", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_review_events")),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["finding_reviews.id"],
            name=op.f("fk_finding_review_events_review_id_finding_reviews"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_finding_review_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        op.f("ix_finding_review_events_review_id"),
        "finding_review_events",
        ["review_id"],
    )
    op.create_index(
        op.f("ix_finding_review_events_actor_id"),
        "finding_review_events",
        ["actor_id"],
    )

    # --- final human decision ---------------------------------------------------
    op.create_table(
        "inspection_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=48), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evaluation_id", sa.Uuid(), nullable=True),
        sa.Column("supersedes_decision_id", sa.Uuid(), nullable=True),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_decisions")),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_inspection_decisions_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_inspection_decisions_decided_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["compliance_evaluations.id"],
            name=op.f(
                "fk_inspection_decisions_evaluation_id_compliance_evaluations"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_decision_id"],
            ["inspection_decisions.id"],
            name=op.f(
                "fk_inspection_decisions_supersedes_decision_id_inspection_decisions"
            ),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_inspection_decisions_inspection_id"),
        "inspection_decisions",
        ["inspection_id"],
    )
    op.create_index(
        op.f("ix_inspection_decisions_decision"), "inspection_decisions", ["decision"]
    )
    op.create_index(
        op.f("ix_inspection_decisions_decided_by"),
        "inspection_decisions",
        ["decided_by"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inspection_decisions_decided_by"), table_name="inspection_decisions"
    )
    op.drop_index(
        op.f("ix_inspection_decisions_decision"), table_name="inspection_decisions"
    )
    op.drop_index(
        op.f("ix_inspection_decisions_inspection_id"),
        table_name="inspection_decisions",
    )
    op.drop_table("inspection_decisions")
    op.drop_index(
        op.f("ix_finding_review_events_actor_id"), table_name="finding_review_events"
    )
    op.drop_index(
        op.f("ix_finding_review_events_review_id"), table_name="finding_review_events"
    )
    op.drop_table("finding_review_events")
    op.drop_index(op.f("ix_finding_reviews_reviewed_by"), table_name="finding_reviews")
    op.drop_index(op.f("ix_finding_reviews_state"), table_name="finding_reviews")
    op.drop_index(op.f("ix_finding_reviews_inspection_id"), table_name="finding_reviews")
    op.drop_index(op.f("ix_finding_reviews_finding_id"), table_name="finding_reviews")
    op.drop_table("finding_reviews")
    op.drop_index(
        op.f("ix_field_corrections_corrected_by"), table_name="field_corrections"
    )
    op.drop_index(
        op.f("ix_field_corrections_inspection_id"), table_name="field_corrections"
    )
    op.drop_index(
        op.f("ix_field_corrections_extracted_field_id"), table_name="field_corrections"
    )
    op.drop_table("field_corrections")
    op.drop_index(
        op.f("ix_extracted_fields_corrected_by"), table_name="extracted_fields"
    )
    with op.batch_alter_table("extracted_fields") as batch:
        batch.drop_column("corrected_reason")
        batch.drop_column("corrected_by")
