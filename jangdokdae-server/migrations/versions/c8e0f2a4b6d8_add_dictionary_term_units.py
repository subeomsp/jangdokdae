"""add dictionary term units and per-term aliases

Revision ID: c8e0f2a4b6d8
Revises: b7d9e1f3a5c7
Create Date: 2026-07-20 20:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8e0f2a4b6d8"
down_revision: str | Sequence[str] | None = "b7d9e1f3a5c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dictionary_source_entries",
        sa.Column(
            "term_units",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "dictionary_source_entries",
        sa.Column(
            "term_units_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "dictionary_source_entries",
        sa.Column("term_units_model_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "dictionary_source_entries",
        sa.Column("term_units_reviewed_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_dictionary_source_entries_term_units_status",
        "dictionary_source_entries",
        ["term_units_status"],
        unique=False,
    )

    op.add_column(
        "dictionary_terms",
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "dictionary_terms",
        sa.Column("source_unit_index", sa.Integer(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_dictionary_terms_source_entry_unit",
        "dictionary_terms",
        ["source_entry_id", "source_unit_index"],
    )

    # 이미 원문 기반 검증을 통과한 표본은 단일 용어 계획으로 안전하게 승격한다.
    op.execute(
        """
        UPDATE dictionary_terms AS dt
        SET aliases = dse.aliases,
            source_unit_index = 0
        FROM dictionary_source_entries AS dse
        WHERE dt.source_entry_id = dse.id
          AND dt.source = 'bok_800'
          AND dt.verification_status = 'verified'
        """
    )
    op.execute(
        """
        UPDATE dictionary_source_entries AS dse
        SET term_units = jsonb_build_array(
                jsonb_build_object(
                    'unit_index', 0,
                    'term', dt.term,
                    'aliases', dt.aliases,
                    'relationship', 'single'
                )
            ),
            term_units_status = 'approved',
            term_units_reviewed_at = (now() AT TIME ZONE 'Asia/Seoul')
        FROM dictionary_terms AS dt
        WHERE dt.source_entry_id = dse.id
          AND dt.source = 'bok_800'
          AND dt.verification_status = 'verified'
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_dictionary_terms_source_entry_unit",
        "dictionary_terms",
        type_="unique",
    )
    op.drop_column("dictionary_terms", "source_unit_index")
    op.drop_column("dictionary_terms", "aliases")

    op.drop_index(
        "ix_dictionary_source_entries_term_units_status",
        table_name="dictionary_source_entries",
    )
    op.drop_column("dictionary_source_entries", "term_units_reviewed_at")
    op.drop_column("dictionary_source_entries", "term_units_model_name")
    op.drop_column("dictionary_source_entries", "term_units_status")
    op.drop_column("dictionary_source_entries", "term_units")
