"""add dictionary term generation prompt version

Revision ID: e0a2b4c6d8f0
Revises: d9f1a3c5e7b9
Create Date: 2026-07-20 20:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e0a2b4c6d8f0"
down_revision: str | Sequence[str] | None = "d9f1a3c5e7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dictionary_terms",
        sa.Column("generation_prompt_version", sa.String(length=80), nullable=True),
    )
    # 현재 DB의 한국은행 원문 기반 생성 표본은 용어별 분리 강화 전 프롬프트를 사용했다.
    op.execute(
        """
        UPDATE dictionary_terms
        SET generation_prompt_version = 'bok-definition-v1'
        WHERE source = 'bok_800'
          AND generation_prompt_version IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("dictionary_terms", "generation_prompt_version")
