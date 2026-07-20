"""add dictionary source entries and provenance fields

Revision ID: b7d9e1f3a5c7
Revises: a4c6e8f0b2d4
Create Date: 2026-07-20 17:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d9e1f3a5c7"
down_revision: str | Sequence[str] | None = "a4c6e8f0b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dictionary_source_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=40), nullable=False),
        sa.Column("source_title", sa.String(length=200), nullable=False),
        sa.Column("source_version", sa.String(length=40), nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("raw_definition", sa.Text(), nullable=False),
        sa.Column(
            "related_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_pdf_url", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("pdf_page", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "is_selected",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("selection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("(now() AT TIME ZONE 'Asia/Seoul')"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_code",
            "source_version",
            "term",
            name="uq_dictionary_source_entries_source_version_term",
        ),
    )
    op.create_index(
        "ix_dictionary_source_entries_term",
        "dictionary_source_entries",
        ["term"],
        unique=False,
    )
    op.create_index(
        "ix_dictionary_source_entries_selected",
        "dictionary_source_entries",
        ["is_selected"],
        unique=False,
    )

    op.add_column(
        "dictionary_terms",
        sa.Column("source_entry_id", sa.Integer(), nullable=True),
    )
    op.add_column("dictionary_terms", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("dictionary_terms", sa.Column("source_page", sa.Integer(), nullable=True))
    op.add_column(
        "dictionary_terms",
        sa.Column(
            "is_ai_generated",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "dictionary_terms",
        sa.Column(
            "verification_status",
            sa.String(length=20),
            server_default=sa.text("'legacy'"),
            nullable=False,
        ),
    )
    op.add_column("dictionary_terms", sa.Column("quality_score", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_dictionary_terms_source_entry_id",
        "dictionary_terms",
        "dictionary_source_entries",
        ["source_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dictionary_terms_source_entry_id",
        "dictionary_terms",
        type_="foreignkey",
    )
    op.drop_column("dictionary_terms", "quality_score")
    op.drop_column("dictionary_terms", "verification_status")
    op.drop_column("dictionary_terms", "is_ai_generated")
    op.drop_column("dictionary_terms", "source_page")
    op.drop_column("dictionary_terms", "source_url")
    op.drop_column("dictionary_terms", "source_entry_id")

    op.drop_index(
        "ix_dictionary_source_entries_selected",
        table_name="dictionary_source_entries",
    )
    op.drop_index(
        "ix_dictionary_source_entries_term",
        table_name="dictionary_source_entries",
    )
    op.drop_table("dictionary_source_entries")
