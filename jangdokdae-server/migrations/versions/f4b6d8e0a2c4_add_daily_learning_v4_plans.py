"""add daily learning v4 plans

Revision ID: f4b6d8e0a2c4
Revises: e0a2b4c6d8f0
Create Date: 2026-07-28 13:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4b6d8e0a2c4"
down_revision: str | Sequence[str] | None = "e0a2b4c6d8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learning_date", sa.Date(), nullable=False, unique=True),
        sa.Column("selection_model", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column(
            "compared_issue_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::integer[]"),
        ),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column(
            "repair_attempted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(now() AT TIME ZONE 'Asia/Seoul')"),
        ),
    )
    op.create_table(
        "daily_learning_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("daily_learning_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issue_docent_id",
            sa.Integer(),
            sa.ForeignKey("issue_docent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "plan_id", "role", name="uq_daily_learning_plan_item_role"
        ),
        sa.UniqueConstraint(
            "plan_id", "position", name="uq_daily_learning_plan_item_position"
        ),
        sa.UniqueConstraint(
            "plan_id",
            "issue_docent_id",
            name="uq_daily_learning_plan_item_issue",
        ),
    )
    op.create_index(
        "ix_daily_learning_plan_items_plan_id",
        "daily_learning_plan_items",
        ["plan_id"],
    )
    op.create_index(
        "ix_daily_learning_plan_items_issue_docent_id",
        "daily_learning_plan_items",
        ["issue_docent_id"],
    )
    op.create_table(
        "daily_learning_candidate_judgments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("daily_learning_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issue_docent_id",
            sa.Integer(),
            sa.ForeignKey("issue_docent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("learn_value", sa.Integer(), nullable=False),
        sa.Column("focus_fit", sa.Integer(), nullable=False),
        sa.Column("context_fit", sa.Integer(), nullable=False),
        sa.Column("discovery_fit", sa.Integer(), nullable=False),
        sa.Column("explains_why", sa.Boolean(), nullable=False),
        sa.Column("topic_overlap", sa.Boolean(), nullable=False),
        sa.Column("has_new_development", sa.Boolean(), nullable=False),
        sa.Column(
            "matched_previous_issue_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::integer[]"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column(
            "judged_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(now() AT TIME ZONE 'Asia/Seoul')"),
        ),
        sa.UniqueConstraint(
            "plan_id",
            "issue_docent_id",
            name="uq_daily_learning_candidate_judgment_issue",
        ),
    )
    op.create_index(
        "ix_daily_learning_candidate_judgments_plan_id",
        "daily_learning_candidate_judgments",
        ["plan_id"],
    )
    op.create_index(
        "ix_daily_learning_candidate_judgments_issue_docent_id",
        "daily_learning_candidate_judgments",
        ["issue_docent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_learning_candidate_judgments_issue_docent_id",
        table_name="daily_learning_candidate_judgments",
    )
    op.drop_index(
        "ix_daily_learning_candidate_judgments_plan_id",
        table_name="daily_learning_candidate_judgments",
    )
    op.drop_table("daily_learning_candidate_judgments")
    op.drop_index(
        "ix_daily_learning_plan_items_issue_docent_id",
        table_name="daily_learning_plan_items",
    )
    op.drop_index(
        "ix_daily_learning_plan_items_plan_id",
        table_name="daily_learning_plan_items",
    )
    op.drop_table("daily_learning_plan_items")
    op.drop_table("daily_learning_plans")
