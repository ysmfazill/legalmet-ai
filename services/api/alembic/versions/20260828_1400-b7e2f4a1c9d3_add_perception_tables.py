"""add perception tables + columns (Prompt 4)

Creates the perception provenance tables (``processing_runs``,
``ocr_text_results``) and adds the Prompt 4 columns to ``image_regions`` and
``extracted_fields``:

    image_regions:     processing_run_id, payload
    extracted_fields:  processing_run_id, source_ocr_result_id, status,
                       corrected_value, corrected_at

Development and the test suite build the schema from the ORM via
``Base.metadata.create_all`` and therefore already have these; this migration
keeps the *production* (Alembic-managed) schema in step with the models. All
changes are additive and safe on a populated table — the one NOT NULL column
(``extracted_fields.status``) carries a ``server_default`` matching the
model's Python-side default.

Revision ID: b7e2f4a1c9d3
Revises: a1f3c9d5e2b7
Create Date: 2026-08-28 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2f4a1c9d3"
down_revision: str | None = "a1f3c9d5e2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=16), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ocr_provider", sa.String(length=64), nullable=True),
        sa.Column("ocr_model", sa.String(length=120), nullable=True),
        sa.Column("ocr_version", sa.String(length=64), nullable=True),
        sa.Column("vision_provider", sa.String(length=64), nullable=True),
        sa.Column("vision_model", sa.String(length=120), nullable=True),
        sa.Column("vision_version", sa.String(length=64), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("configuration", _json(), nullable=True),
        sa.Column("summary", _json(), nullable=True),
        sa.Column("error", _json(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["inspection_id"], ["inspections.id"], ondelete="CASCADE",
            name=op.f("fk_processing_runs_inspection_id_inspections"),
        ),
        sa.ForeignKeyConstraint(
            ["image_id"], ["images.id"], ondelete="CASCADE",
            name=op.f("fk_processing_runs_image_id_images"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_runs")),
    )
    with op.batch_alter_table("processing_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_processing_runs_reference"), ["reference"], unique=True)
        batch_op.create_index(batch_op.f("ix_processing_runs_inspection_id"), ["inspection_id"])
        batch_op.create_index(batch_op.f("ix_processing_runs_image_id"), ["image_id"])
        batch_op.create_index(batch_op.f("ix_processing_runs_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_processing_runs_created_at"), ["created_at"])

    op.create_table(
        "ocr_text_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("region_id", sa.Uuid(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("bbox", _json(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["image_id"], ["images.id"], ondelete="CASCADE",
            name=op.f("fk_ocr_text_results_image_id_images"),
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id"], ["processing_runs.id"], ondelete="CASCADE",
            name=op.f("fk_ocr_text_results_processing_run_id_processing_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["region_id"], ["image_regions.id"], ondelete="SET NULL",
            name=op.f("fk_ocr_text_results_region_id_image_regions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocr_text_results")),
    )
    with op.batch_alter_table("ocr_text_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ocr_text_results_image_id"), ["image_id"])
        batch_op.create_index(
            batch_op.f("ix_ocr_text_results_processing_run_id"), ["processing_run_id"]
        )
        batch_op.create_index(batch_op.f("ix_ocr_text_results_region_id"), ["region_id"])
        batch_op.create_index(batch_op.f("ix_ocr_text_results_created_at"), ["created_at"])

    with op.batch_alter_table("image_regions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "processing_run_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "processing_runs.id",
                    ondelete="CASCADE",
                    name=op.f("fk_image_regions_processing_run_id_processing_runs"),
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("payload", _json(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_image_regions_processing_run_id"), ["processing_run_id"]
        )

    with op.batch_alter_table("extracted_fields", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "processing_run_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "processing_runs.id",
                    ondelete="CASCADE",
                    name=op.f("fk_extracted_fields_processing_run_id_processing_runs"),
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_ocr_result_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "ocr_text_results.id",
                    ondelete="SET NULL",
                    name=op.f("fk_extracted_fields_source_ocr_result_id_ocr_text_results"),
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=24),
                nullable=False,
                server_default="DETECTED",
            )
        )
        batch_op.add_column(sa.Column("corrected_value", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_extracted_fields_processing_run_id"), ["processing_run_id"]
        )
        batch_op.create_index(
            batch_op.f("ix_extracted_fields_source_ocr_result_id"), ["source_ocr_result_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("extracted_fields", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extracted_fields_source_ocr_result_id"))
        batch_op.drop_index(batch_op.f("ix_extracted_fields_processing_run_id"))
        batch_op.drop_column("corrected_at")
        batch_op.drop_column("corrected_value")
        batch_op.drop_column("status")
        batch_op.drop_column("source_ocr_result_id")
        batch_op.drop_column("processing_run_id")

    with op.batch_alter_table("image_regions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_image_regions_processing_run_id"))
        batch_op.drop_column("payload")
        batch_op.drop_column("processing_run_id")

    op.drop_table("ocr_text_results")
    op.drop_table("processing_runs")
