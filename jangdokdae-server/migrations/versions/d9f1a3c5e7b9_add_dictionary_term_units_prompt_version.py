"""add dictionary term units prompt version

Revision ID: d9f1a3c5e7b9
Revises: c8e0f2a4b6d8
Create Date: 2026-07-20 20:08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9f1a3c5e7b9"
down_revision: str | Sequence[str] | None = "c8e0f2a4b6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dictionary_source_entries",
        sa.Column("term_units_prompt_version", sa.String(length=80), nullable=True),
    )
    # 이번 마이그레이션 전에 생성된 8개 제안과 1개 승인 표본은 모두 v1 규칙을 사용했다.
    op.execute(
        """
        UPDATE dictionary_source_entries
        SET term_units_prompt_version = 'bok-term-units-v1'
        WHERE term_units_status IN ('proposed', 'approved')
          AND term_units_prompt_version IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("dictionary_source_entries", "term_units_prompt_version")
