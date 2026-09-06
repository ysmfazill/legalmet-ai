"""citizen complaint lifecycle (UI-03): state machine + history + links

Extends the UI-02 citizen tables for complaint management:

* ``citizen_reports`` gains:
    - updated_at (lifecycle timestamps)
    - screening_risk / official_priority (SYSTEM screening vs OFFICIAL
      priority decision — deliberately two columns, never one "risk" value)
    - pending_info_request (what the department asked the citizen for)
    - assigned_inspector_id → users.id
    - inspection_id → inspections.id (the complaint → inspection link)
* NEW ``citizen_report_events`` — the immutable complaint-history table the
  citizen timeline and the department trail read. Only real recorded events
  are ever inserted; pending timeline steps are derived, never stored.

Existing UI-02 rows are preserved: their status stays SUBMITTED (a legal
initial state of the new machine) and their evidence snapshot is untouched.

Reversible via ``downgrade`` (drops the events table, removes the new
columns and indexes).

Revision ID: j2d8e4f6a8b0
Revises: h1c7f0b2d4e6
Create Date: 2026-09-05 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j2d8e4f6a8b0"
down_revision: str | None = "h1c7f0b2d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table (table copy) — plain SQLite ALTER cannot add a NOT NULL
    # column with a non-constant default, nor add FKs to an existing table.
    with op.batch_alter_table("citizen_reports", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.add_column(
            sa.Column("screening_risk", sa.String(length=16), nullable=True)
        )
        batch.add_column(
            sa.Column("official_priority", sa.String(length=16), nullable=True)
        )
        batch.add_column(sa.Column("pending_info_request", sa.Text(), nullable=True))
        batch.add_column(sa.Column("assigned_inspector_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_citizen_reports_assigned_inspector_id_users",
            "users",
            ["assigned_inspector_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_citizen_reports_assigned_inspector_id",
            ["assigned_inspector_id"],
        )
        batch.add_column(sa.Column("inspection_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_citizen_reports_inspection_id_inspections",
            "inspections",
            ["inspection_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_citizen_reports_inspection_id", ["inspection_id"])

    op.create_table(
        "citizen_report_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey(
                "citizen_reports.id",
                name="fk_citizen_report_events_report_id_citizen_reports",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_citizen_report_events_actor_id_users",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_citizen_report_events_report_id", "citizen_report_events", ["report_id"])
    op.create_index("ix_citizen_report_events_event", "citizen_report_events", ["event"])
    op.create_index("ix_citizen_report_events_created_at", "citizen_report_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_citizen_report_events_created_at", table_name="citizen_report_events")
    op.drop_index("ix_citizen_report_events_event", table_name="citizen_report_events")
    op.drop_index("ix_citizen_report_events_report_id", table_name="citizen_report_events")
    op.drop_table("citizen_report_events")

    with op.batch_alter_table("citizen_reports", schema=None) as batch:
        batch.drop_index("ix_citizen_reports_inspection_id")
        batch.drop_constraint(
            "fk_citizen_reports_inspection_id_inspections", type_="foreignkey"
        )
        batch.drop_column("inspection_id")
        batch.drop_index("ix_citizen_reports_assigned_inspector_id")
        batch.drop_constraint(
            "fk_citizen_reports_assigned_inspector_id_users", type_="foreignkey"
        )
        batch.drop_column("assigned_inspector_id")
        batch.drop_column("pending_info_request")
        batch.drop_column("official_priority")
        batch.drop_column("screening_risk")
        batch.drop_column("updated_at")
