"""add regulatory intelligence provenance (Prompt 5)

Creates the ``regulatory_sources`` table (top of the provenance hierarchy) and
adds Prompt 5 columns to the existing regulatory tables:

    regulatory_sources:   new table
    regulations:          source_id, document_identifier, document_type,
                          publication_date, content_hash
    regulation_versions:  publication_date
    rules:                requirement_type, field_key, expected_format,
                          mandatory, applicability_definition, source_reference

Development and the test suite build the schema from the ORM via
``Base.metadata.create_all`` and therefore already have these; this migration
keeps the *production* (Alembic-managed) schema in step with the models. All
changes are additive (nullable columns + one table with defaults) and safe on
a populated database — existing DEMO regulatory data and all Prompt 4
perception tables are untouched. Fully reversible via ``downgrade``.

Revision ID: c4d1e8f2a907
Revises: b7e2f4a1c9d3
Create Date: 2026-08-28 16:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d1e8f2a907"
down_revision: str | None = "b7e2f4a1c9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "regulatory_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("canonical_url", sa.String(length=1024), nullable=True),
        sa.Column("jurisdiction", sa.String(length=120), nullable=False),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regulatory_sources")),
        sa.UniqueConstraint("name", name=op.f("uq_regulatory_sources_name")),
    )
    op.create_index(
        op.f("ix_regulatory_sources_source_type"),
        "regulatory_sources",
        ["source_type"],
    )
    op.create_index(
        op.f("ix_regulatory_sources_verification_status"),
        "regulatory_sources",
        ["verification_status"],
    )
    op.create_index(
        op.f("ix_regulatory_sources_created_at"),
        "regulatory_sources",
        ["created_at"],
    )

    # batch_alter_table keeps this portable: on PostgreSQL it emits plain
    # ALTERs, on SQLite (no ALTER CONSTRAINT support) it uses copy-and-move.
    with op.batch_alter_table("regulations") as batch:
        batch.add_column(sa.Column("source_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("document_identifier", sa.String(length=255), nullable=True))
        batch.add_column(
            sa.Column(
                "document_type",
                sa.String(length=48),
                nullable=False,
                server_default="OTHER",
            )
        )
        batch.add_column(sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("content_hash", sa.String(length=128), nullable=True))
        batch.create_index(op.f("ix_regulations_source_id"), ["source_id"])
        batch.create_foreign_key(
            op.f("fk_regulations_source_id_regulatory_sources"),
            "regulatory_sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("regulation_versions") as batch:
        batch.add_column(sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("rules") as batch:
        batch.add_column(
            sa.Column(
                "requirement_type",
                sa.String(length=32),
                nullable=False,
                server_default="DECLARATION",
            )
        )
        batch.add_column(sa.Column("field_key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("expected_format", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        # Server default keeps the NOT NULL add safe on a populated table
        # (existing demo rules get an empty definition).
        batch.add_column(
            sa.Column("applicability_definition", _json(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(sa.Column("source_reference", sa.String(length=255), nullable=True))
        batch.create_index(op.f("ix_rules_field_key"), ["field_key"])


def downgrade() -> None:
    with op.batch_alter_table("rules") as batch:
        batch.drop_index(op.f("ix_rules_field_key"))
        batch.drop_column("source_reference")
        batch.drop_column("applicability_definition")
        batch.drop_column("mandatory")
        batch.drop_column("expected_format")
        batch.drop_column("field_key")
        batch.drop_column("requirement_type")

    with op.batch_alter_table("regulation_versions") as batch:
        batch.drop_column("publication_date")

    with op.batch_alter_table("regulations") as batch:
        batch.drop_constraint(
            op.f("fk_regulations_source_id_regulatory_sources"),
            type_="foreignkey",
        )
        batch.drop_index(op.f("ix_regulations_source_id"))
        batch.drop_column("content_hash")
        batch.drop_column("publication_date")
        batch.drop_column("document_type")
        batch.drop_column("document_identifier")
        batch.drop_column("source_id")

    op.drop_index(
        op.f("ix_regulatory_sources_created_at"), table_name="regulatory_sources"
    )
    op.drop_index(
        op.f("ix_regulatory_sources_verification_status"),
        table_name="regulatory_sources",
    )
    op.drop_index(
        op.f("ix_regulatory_sources_source_type"), table_name="regulatory_sources"
    )
    op.drop_table("regulatory_sources")
