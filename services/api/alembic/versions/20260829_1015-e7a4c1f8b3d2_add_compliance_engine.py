"""add deterministic compliance engine (Prompt 6)

Creates the compliance-engine tables:

    compliance_evaluations:  one deterministic evaluation run per inspection
                             (immutable-by-convention — never overwritten)
    compliance_rules:        deterministic rule configurations bound to real
                             Prompt 5 requirements (FK rules.id)
    evaluation_findings:     one finding per (evaluation, requirement), each
                             with detected/expected values, deterministic
                             explanation, frozen provenance snapshot and
                             evidence references

Development and the test suite build the schema from the ORM via
``Base.metadata.create_all`` and therefore already have these; this migration
keeps the *production* (Alembic-managed) schema in step with the models.

The change is purely additive (three new tables; no existing table is
touched), so it is safe on a populated database — the Prompt 1 demo
compliance_findings / evidence tables and all Prompt 4/5 data are unaffected.
Fully reversible via ``downgrade`` (drop the three tables).

Revision ID: e7a4c1f8b3d2
Revises: c4d1e8f2a907
Create Date: 2026-08-29 10:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a4c1f8b3d2"
down_revision: str | None = "c4d1e8f2a907"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "compliance_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("rule_code", sa.String(length=128), nullable=False),
        sa.Column("rule_type", sa.String(length=48), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("configuration", _json(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_rules")),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["rules.id"],
            name=op.f("fk_compliance_rules_requirement_id_rules"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_compliance_rules_requirement_id"),
        "compliance_rules",
        ["requirement_id"],
    )
    op.create_index(op.f("ix_compliance_rules_rule_code"), "compliance_rules", ["rule_code"])

    op.create_table(
        "compliance_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=True),
        sa.Column("regulatory_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("engine_version", sa.String(length=48), nullable=False),
        sa.Column("context_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", _json(), nullable=False),
        sa.Column("error", _json(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_evaluations")),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_compliance_evaluations_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["images.id"],
            name=op.f("fk_compliance_evaluations_image_id_images"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["regulatory_version_id"],
            ["regulation_versions.id"],
            name=op.f(
                "fk_compliance_evaluations_regulatory_version_id_regulation_versions"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_compliance_evaluations_actor_id_users"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_compliance_evaluations_inspection_id"),
        "compliance_evaluations",
        ["inspection_id"],
    )
    op.create_index(
        op.f("ix_compliance_evaluations_status"), "compliance_evaluations", ["status"]
    )

    op.create_table(
        "evaluation_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("extracted_field_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_region_id", sa.Uuid(), nullable=True),
        sa.Column("image_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("applicability", sa.String(length=16), nullable=False),
        sa.Column("detected_value", sa.Text(), nullable=True),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("provenance", _json(), nullable=False),
        sa.Column("detail", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_findings")),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["compliance_evaluations.id"],
            name=op.f("fk_evaluation_findings_evaluation_id_compliance_evaluations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["rules.id"],
            name=op.f("fk_evaluation_findings_requirement_id_rules"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["compliance_rules.id"],
            name=op.f("fk_evaluation_findings_rule_id_compliance_rules"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["extracted_field_id"],
            ["extracted_fields.id"],
            name=op.f("fk_evaluation_findings_extracted_field_id_extracted_fields"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_region_id"],
            ["image_regions.id"],
            name=op.f("fk_evaluation_findings_evidence_region_id_image_regions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["images.id"],
            name=op.f("fk_evaluation_findings_image_id_images"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_evaluation_findings_evaluation_id"),
        "evaluation_findings",
        ["evaluation_id"],
    )
    op.create_index(
        op.f("ix_evaluation_findings_requirement_id"),
        "evaluation_findings",
        ["requirement_id"],
    )
    op.create_index(
        op.f("ix_evaluation_findings_extracted_field_id"),
        "evaluation_findings",
        ["extracted_field_id"],
    )
    op.create_index(
        op.f("ix_evaluation_findings_rule_id"), "evaluation_findings", ["rule_id"]
    )
    op.create_index(op.f("ix_evaluation_findings_status"), "evaluation_findings", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_findings_status"), table_name="evaluation_findings")
    op.drop_index(op.f("ix_evaluation_findings_rule_id"), table_name="evaluation_findings")
    op.drop_index(
        op.f("ix_evaluation_findings_extracted_field_id"), table_name="evaluation_findings"
    )
    op.drop_index(
        op.f("ix_evaluation_findings_requirement_id"), table_name="evaluation_findings"
    )
    op.drop_index(
        op.f("ix_evaluation_findings_evaluation_id"), table_name="evaluation_findings"
    )
    op.drop_table("evaluation_findings")
    op.drop_index(
        op.f("ix_compliance_evaluations_status"), table_name="compliance_evaluations"
    )
    op.drop_index(
        op.f("ix_compliance_evaluations_inspection_id"),
        table_name="compliance_evaluations",
    )
    op.drop_table("compliance_evaluations")
    op.drop_index(op.f("ix_compliance_rules_rule_code"), table_name="compliance_rules")
    op.drop_index(
        op.f("ix_compliance_rules_requirement_id"), table_name="compliance_rules"
    )
    op.drop_table("compliance_rules")
