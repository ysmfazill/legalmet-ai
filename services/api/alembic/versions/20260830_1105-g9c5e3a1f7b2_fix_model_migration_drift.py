"""fix model/migration schema drift (Prompt 9, Phase 9)

Two columns exist on the ORM models but were never created by the migration
chain (the dev database was built with ``create_all``, which masked the gap —
a production database provisioned purely via Alembic would fail at runtime
with "no such column"):

    packages.status                    (Prompt 3 package lifecycle; ORM default CREATED)
    field_corrections.created_at       (Prompt 8; ORM-created timestamp)

The fix is purely additive and safe on populated databases: both columns are
NOT NULL with a server default, so existing rows backfill automatically.
Reversible via ``downgrade`` (drops the two columns).

Revision ID: g9c5e3a1f7b2
Revises: f8b2d6a4c1e9
Create Date: 2026-08-30 11:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g9c5e3a1f7b2"
down_revision: str | None = "f8b2d6a4c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Package intake lifecycle status (matches Package model / PackageStatus).
    with op.batch_alter_table("packages") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="CREATED",
            )
        )

    # created_at on the append-only field-correction history (matches the
    # FieldCorrection model's TimestampMixin).
    with op.batch_alter_table("field_corrections") as batch:
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )

    # The Prompt 8 migration added extracted_fields.corrected_by as a bare
    # column; the model declares a FK to users (ondelete SET NULL). Materialise
    # the constraint so a migrated database enforces the same integrity the
    # ORM promises.
    with op.batch_alter_table("extracted_fields") as batch:
        batch.create_foreign_key(
            "fk_extracted_fields_corrected_by_users",
            "users",
            ["corrected_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("extracted_fields") as batch:
        batch.drop_constraint("fk_extracted_fields_corrected_by_users", type_="foreignkey")
    with op.batch_alter_table("field_corrections") as batch:
        batch.drop_column("created_at")
    with op.batch_alter_table("packages") as batch:
        batch.drop_column("status")
