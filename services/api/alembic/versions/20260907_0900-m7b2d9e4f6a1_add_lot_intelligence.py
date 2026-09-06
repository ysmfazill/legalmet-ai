"""lot intelligence + measurement evaluation (UI-07)

New tables:

* ``lots`` — one lot under physical verification within an inspection
  (declared quantity preserved verbatim, lot size, decision fields; the
  status only changes through an explicit gated inspector submission).
* ``lot_packages`` — package records belonging to a lot, with their
  sampling state (NOT_SAMPLED / PENDING / MEASURED).
* ``sampling_runs`` — one audited, reproducible sample draw: size, method,
  configured-procedure reference (or an explicit AI-recommended label),
  randomization seed/metadata.
* ``measurement_evaluations`` — one deterministic declared-vs-measured
  regulatory evaluation per verification result, freezing the rule code,
  regulation version and computed inputs. UNAVAILABLE (never a guessed
  tolerance) when no permissible-error procedure is configured.
* ``regulatory_procedures`` — versioned procedures that govern physical
  work (measurement tolerance, legal sampling), bound to a
  ``regulation_versions`` row so historical evaluations keep the procedure
  they were evaluated under.

Column addition:

* ``verification_tasks.lot_package_id`` — anchor C: a lot-anchored
  measurement task. Lot-anchored tasks gate the LOT decision, not the
  inspection decision.

Reversible via ``downgrade``.

Revision ID: m7b2d9e4f6a1
Revises: k3f6a8c2e1b4
Create Date: 2026-09-07 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m7b2d9e4f6a1"
down_revision: str | None = "k3f6a8c2e1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "inspection_id",
            sa.Uuid(),
            sa.ForeignKey(
                "inspections.id",
                name="fk_lots_inspection_id_inspections",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey(
                "products.id",
                name="fk_lots_product_id_products",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("declared_value", sa.String(length=64), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_lots_created_by_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "decided_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_lots_decided_by_users",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_lots_inspection_id", "lots", ["inspection_id"])
    op.create_index("ix_lots_status", "lots", ["status"])
    op.create_index("ix_lots_created_by", "lots", ["created_by"])
    op.create_index("ix_lots_created_at", "lots", ["created_at"])

    op.create_table(
        "sampling_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "lot_id",
            sa.Uuid(),
            sa.ForeignKey(
                "lots.id",
                name="fk_sampling_runs_lot_id_lots",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("selection_method", sa.String(length=24), nullable=False),
        sa.Column("procedure_code", sa.String(length=128), nullable=True),
        sa.Column("procedure_version_label", sa.String(length=128), nullable=True),
        sa.Column("is_ai_recommended", sa.Boolean(), nullable=False),
        sa.Column("seed", sa.String(length=64), nullable=True),
        sa.Column("randomization", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_sampling_runs_created_by_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
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
    op.create_index("ix_sampling_runs_lot_id", "sampling_runs", ["lot_id"])
    op.create_index("ix_sampling_runs_created_by", "sampling_runs", ["created_by"])
    op.create_index("ix_sampling_runs_created_at", "sampling_runs", ["created_at"])

    op.create_table(
        "lot_packages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "lot_id",
            sa.Uuid(),
            sa.ForeignKey(
                "lots.id",
                name="fk_lot_packages_lot_id_lots",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column(
            "package_id",
            sa.Uuid(),
            sa.ForeignKey(
                "packages.id",
                name="fk_lot_packages_package_id_packages",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "sampling_run_id",
            sa.Uuid(),
            sa.ForeignKey(
                "sampling_runs.id",
                name="fk_lot_packages_sampling_run_id_sampling_runs",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
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
    op.create_index("ix_lot_packages_lot_id", "lot_packages", ["lot_id"])
    op.create_index("ix_lot_packages_status", "lot_packages", ["status"])
    op.create_index("ix_lot_packages_sampling_run_id", "lot_packages", ["sampling_run_id"])
    op.create_index("ix_lot_packages_created_at", "lot_packages", ["created_at"])

    # batch_alter_table keeps this portable: SQLite cannot ALTER a constraint
    # in place, so the table is copied with the new FK-bearing column.
    with op.batch_alter_table("verification_tasks") as batch:
        batch.add_column(
            sa.Column(
                "lot_package_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "lot_packages.id",
                    name="fk_verification_tasks_lot_package_id_lot_packages",
                    ondelete="CASCADE",
                ),
                nullable=True,
            ),
        )
    op.create_index(
        "ix_verification_tasks_lot_package_id",
        "verification_tasks",
        ["lot_package_id"],
    )

    op.create_table(
        "measurement_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "verification_result_id",
            sa.Uuid(),
            sa.ForeignKey(
                "verification_results.id",
                name="fk_measurement_evaluations_verification_result_id_verification_results",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "inspection_id",
            sa.Uuid(),
            sa.ForeignKey(
                "inspections.id",
                name="fk_measurement_evaluations_inspection_id_inspections",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("rule_code", sa.String(length=128), nullable=True),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "regulation_versions.id",
                name="fk_measurement_evaluations_rule_version_id_regulation_versions",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_measurement_evaluations_verification_result_id",
        "measurement_evaluations",
        ["verification_result_id"],
        unique=True,
    )
    op.create_index(
        "ix_measurement_evaluations_inspection_id",
        "measurement_evaluations",
        ["inspection_id"],
    )
    op.create_index("ix_measurement_evaluations_status", "measurement_evaluations", ["status"])

    op.create_table(
        "regulatory_procedures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "regulation_version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "regulation_versions.id",
                name="fk_regulatory_procedures_regulation_version_id_regulation_versions",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
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
        "ix_regulatory_procedures_regulation_version_id",
        "regulatory_procedures",
        ["regulation_version_id"],
    )
    op.create_index("ix_regulatory_procedures_kind", "regulatory_procedures", ["kind"])
    op.create_index("ix_regulatory_procedures_code", "regulatory_procedures", ["code"])


def downgrade() -> None:
    op.drop_index("ix_regulatory_procedures_code", table_name="regulatory_procedures")
    op.drop_index("ix_regulatory_procedures_kind", table_name="regulatory_procedures")
    op.drop_index(
        "ix_regulatory_procedures_regulation_version_id",
        table_name="regulatory_procedures",
    )
    op.drop_table("regulatory_procedures")

    op.drop_index("ix_measurement_evaluations_status", table_name="measurement_evaluations")
    op.drop_index(
        "ix_measurement_evaluations_inspection_id",
        table_name="measurement_evaluations",
    )
    op.drop_index(
        "ix_measurement_evaluations_verification_result_id",
        table_name="measurement_evaluations",
    )
    op.drop_table("measurement_evaluations")

    op.drop_index(
        "ix_verification_tasks_lot_package_id", table_name="verification_tasks"
    )
    with op.batch_alter_table("verification_tasks") as batch:
        batch.drop_column("lot_package_id")

    op.drop_index("ix_lot_packages_created_at", table_name="lot_packages")
    op.drop_index("ix_lot_packages_sampling_run_id", table_name="lot_packages")
    op.drop_index("ix_lot_packages_status", table_name="lot_packages")
    op.drop_index("ix_lot_packages_lot_id", table_name="lot_packages")
    op.drop_table("lot_packages")

    op.drop_index("ix_sampling_runs_created_at", table_name="sampling_runs")
    op.drop_index("ix_sampling_runs_created_by", table_name="sampling_runs")
    op.drop_index("ix_sampling_runs_lot_id", table_name="sampling_runs")
    op.drop_table("sampling_runs")

    op.drop_index("ix_lots_created_at", table_name="lots")
    op.drop_index("ix_lots_created_by", table_name="lots")
    op.drop_index("ix_lots_status", table_name="lots")
    op.drop_index("ix_lots_inspection_id", table_name="lots")
    op.drop_table("lots")
