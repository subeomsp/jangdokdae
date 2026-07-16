"""add current snapshot flag to news_cluster

Revision ID: a4c6e8f0b2d4
Revises: f0a1b2c3d4e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c6e8f0b2d4"
down_revision: str | Sequence[str] | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_cluster",
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "ix_news_cluster_current_run",
        "news_cluster",
        ["run_date"],
        unique=False,
        postgresql_where=sa.text("is_current = true"),
    )
    # 정확한 과거 배치 경계는 없지만 stable id별 가장 최근 행을 직전 스냅샷으로 복원하면
    # 다음 실행의 stable id 승계를 유지할 수 있다. 다음 정상 실행이 이를 정확한 스냅샷으로 교체한다.
    op.execute(
        """
        UPDATE news_cluster
           SET is_current = true
         WHERE id IN (
             SELECT DISTINCT ON (stable_id) id
               FROM news_cluster
              WHERE run_date = (SELECT max(run_date) FROM news_cluster)
                AND stable_id IS NOT NULL
              ORDER BY stable_id, id DESC
         )
        """
    )
    op.alter_column("news_cluster", "is_current", server_default=sa.text("true"))


def downgrade() -> None:
    op.drop_index("ix_news_cluster_current_run", table_name="news_cluster")
    op.drop_column("news_cluster", "is_current")
