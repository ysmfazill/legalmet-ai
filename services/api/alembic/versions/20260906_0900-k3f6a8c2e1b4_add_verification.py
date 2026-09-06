"""verification tasks + results (UI-06): the Evidence Planner layer

Two new append-only tables:

* ``verification_tasks`` — one concrete inspector action that closes an
  evidence gap (a physical net-content measurement, a field observation).
  Anchored to an engine finding (``finding_id``) and/or an extracted
  declaration (``extracted_field_id``). Lifecycle PENDING → IN_PROGRESS →
  COMPLETED, or → CANCELLED, enforced in the service layer. ``requirement_
  level`` distinguishes REQUIRED (blocks a final decision while open) from
  RECOMMENDED (advisory, never blocks).
* ``verification_results`` — one recorded outcome per row, never edited:
  measured value + unit (kept SEPARATE from the declared value, which stays
  on the extracted field), instrument id and its verification status (only
  when supplied — absent means "not recorded", never "verified"), observation,
  notes, the recording human and timestamp.

Nothing in this migration evaluates declared-vs-measured against a rule: a
measurement is evidence for the inspector's decision, never an automatic
violation.

Reversible via ``downgrade`` (drops both tables).

Revision ID: k3f6a8c2e1b4
Revises: j2d8e4f6a8b0
Create Date: 2026-09-06 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k3f6a8c2e1b4"
down_revision: str | None = "j2d8e4f6a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verification_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "inspection_id",
            sa.Uuid(),
            sa.ForeignKey(
                "inspections.id",
                name="fk_verification_tasks_inspection_id_inspections",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            sa.Uuid(),
            sa.ForeignKey(
                "evaluation_findings.id",
                name="fk_verification_tasks_finding_id_evaluation_findings",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "extracted_field_id",
            sa.Uuid(),
            sa.ForeignKey(
                "extracted_fields.id",
                name="fk_verification_tasks_extracted_field_id_extracted_fields",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("requirement_level", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_verification_tasks_created_by_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_verification_tasks_inspection_id", "verification_tasks", ["inspection_id"]
    )
    op.create_index("ix_verification_tasks_finding_id", "verification_tasks", ["finding_id"])
    op.create_index(
        "ix_verification_tasks_extracted_field_id",
        "verification_tasks",
        ["extracted_field_id"],
    )
    op.create_index("ix_verification_tasks_status", "verification_tasks", ["status"])
    op.create_index("ix_verification_tasks_created_by", "verification_tasks", ["created_by"])
    op.create_index("ix_verification_tasks_created_at", "verification_tasks", ["created_at"])

    op.create_table(
        "verification_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey(
                "verification_tasks.id",
                name="fk_verification_results_task_id_verification_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "recorded_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_verification_results_recorded_by_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measured_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("instrument_id", sa.String(length=128), nullable=True),
        sa.Column("instrument_verification_status", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_verification_results_task_id", "verification_results", ["task_id"])
    op.create_index(
        "ix_verification_results_recorded_by", "verification_results", ["recorded_by"]
    )
    op.create_index("ix_verification_results_created_at", "verification_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_verification_results_created_at", table_name="verification_results")
    op.drop_index(
        "ix_verification_results_recorded_by", table_name="verification_results"
    )
    op.drop_index("ix_verification_results_task_id", table_name="verification_results")
    op.drop_table("verification_results")
    op.drop_index("ix_verification_tasks_created_by", table_name="verification_tasks")
    op.drop_index("ix_verification_tasks_created_at", table_name="verification_tasks")
    op.drop_index("ix_verification_tasks_status", table_name="verification_tasks")
    op.drop_index(
        "ix_verification_tasks_extracted_field_id", table_name="verification_tasks"
    )
    op.drop_index("ix_verification_tasks_finding_id", table_name="verification_tasks")
    op.drop_index("ix_verification_tasks_inspection_id", table_name="verification_tasks")
    op.drop_table("verification_tasks")
