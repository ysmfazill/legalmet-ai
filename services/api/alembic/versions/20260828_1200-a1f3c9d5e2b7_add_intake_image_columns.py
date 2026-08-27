"""add real-intake image columns (Prompt 3)

Adds the provenance + preprocessing columns introduced by the real
package-intake pipeline to the ``images`` table:

    checksum, capture_source, processing_status, quality_grade,
    quality_metrics, processed_storage_key

Development and the test suite build the schema from the ORM via
``Base.metadata.create_all`` and therefore already have these columns; this
migration keeps the *production* (Alembic-managed) schema in step with the
model. Columns are additive and safe on a populated table — the two NOT NULL
columns carry a ``server_default`` matching the model's Python-side default.

Revision ID: a1f3c9d5e2b7
Revises: 3d657d928700
Create Date: 2026-08-28 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f3c9d5e2b7"
down_revision: str | None = "3d657d928700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("checksum", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "capture_source",
                sa.String(length=16),
                nullable=False,
                server_default="UPLOAD",
            )
        )
        batch_op.add_column(
            sa.Column(
                "processing_status",
                sa.String(length=16),
                nullable=False,
                server_default="PENDING",
            )
        )
        batch_op.add_column(sa.Column("quality_grade", sa.String(length=16), nullable=True))
        batch_op.add_column(
            sa.Column(
                "quality_metrics",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("processed_storage_key", sa.String(length=512), nullable=True)
        )
        batch_op.create_index(batch_op.f("ix_images_checksum"), ["checksum"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_images_checksum"))
        batch_op.drop_column("processed_storage_key")
        batch_op.drop_column("quality_metrics")
        batch_op.drop_column("quality_grade")
        batch_op.drop_column("processing_status")
        batch_op.drop_column("capture_source")
        batch_op.drop_column("checksum")
