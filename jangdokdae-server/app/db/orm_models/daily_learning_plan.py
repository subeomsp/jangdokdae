"""v4 일일 학습 편집 계획과 후보 판정 결과."""

from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import KST_NOW, Base


class DailyLearningPlan(Base):
    __tablename__ = "daily_learning_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learning_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    selection_model: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    compared_issue_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    repair_attempted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=KST_NOW
    )


class DailyLearningPlanItem(Base):
    __tablename__ = "daily_learning_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "role", name="uq_daily_learning_plan_item_role"),
        UniqueConstraint(
            "plan_id", "position", name="uq_daily_learning_plan_item_position"
        ),
        UniqueConstraint(
            "plan_id",
            "issue_docent_id",
            name="uq_daily_learning_plan_item_issue",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("daily_learning_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_docent_id: Mapped[int] = mapped_column(
        ForeignKey("issue_docent.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class DailyLearningCandidateJudgment(Base):
    __tablename__ = "daily_learning_candidate_judgments"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "issue_docent_id",
            name="uq_daily_learning_candidate_judgment_issue",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("daily_learning_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_docent_id: Mapped[int] = mapped_column(
        ForeignKey("issue_docent.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    learn_value: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    context_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    discovery_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    explains_why: Mapped[bool] = mapped_column(Boolean, nullable=False)
    topic_overlap: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_new_development: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matched_previous_issue_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    judged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=KST_NOW
    )
