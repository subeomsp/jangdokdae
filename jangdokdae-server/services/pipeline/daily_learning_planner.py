"""파이프라인 마지막 단계 — v4 후보 판정과 일일 기본 학습 계획 고정."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import TypedDict, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.learning import LearningRole
from app.db.orm_models.daily_learning_plan import (
    DailyLearningCandidateJudgment,
    DailyLearningPlan,
    DailyLearningPlanItem,
)
from app.db.orm_models.issue_docent import IssueDocent
from app.db.orm_models.news import News
from app.db.orm_models.news_analysis import NewsAnalysis
from app.db.orm_models.news_cluster import NewsCluster
from services.learning_editorial import (
    HISTORY_DAYS,
    JUDGE_PROMPT_VERSION,
    judge_candidates,
)
from services.learning_scoring import select_daily_v4
from services.learning_selection import (
    LearningCandidate,
    candidate_to_scoring_row,
    load_candidates,
)
from utils.dates import now_kst

SELECTION_MODEL = "v4"
ROLE_ORDER: tuple[LearningRole, ...] = ("focus", "context", "discovery")


class DailyLearningPlannerState(TypedDict):
    learning_date: str
    candidates: int
    selected: int
    repair_attempted: bool
    cached: bool


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


async def _recent_selected_rows(db: AsyncSession, learning_date: date) -> list[dict]:
    since = learning_date - timedelta(days=HISTORY_DAYS)
    rows = (
        await db.execute(
            select(
                DailyLearningPlan.learning_date,
                DailyLearningPlanItem.position,
                IssueDocent,
                NewsCluster,
                NewsAnalysis,
            )
            .join(
                DailyLearningPlanItem,
                DailyLearningPlanItem.plan_id == DailyLearningPlan.id,
            )
            .join(
                IssueDocent,
                IssueDocent.id == DailyLearningPlanItem.issue_docent_id,
            )
            .join(NewsCluster, NewsCluster.id == IssueDocent.cluster_id)
            .join(NewsAnalysis, NewsAnalysis.cluster_id == NewsCluster.id)
            .where(DailyLearningPlan.learning_date >= since)
            .where(DailyLearningPlan.learning_date < learning_date)
            .order_by(
                DailyLearningPlan.learning_date,
                DailyLearningPlanItem.position,
            )
        )
    ).all()
    previous: list[dict] = []
    for selected_on, _, docent, cluster, analysis in rows:
        row = candidate_to_scoring_row(LearningCandidate(docent, cluster, analysis))
        row["_selected_on"] = selected_on.isoformat()
        previous.append(row)
    return previous


async def _similarities(
    db: AsyncSession,
    today: list[dict],
    previous: list[dict],
) -> dict[str, dict[str, float]] | None:
    cluster_ids = {
        int(row["cluster_id"])
        for row in [*today, *previous]
        if row.get("cluster_id") is not None
    }
    if not cluster_ids or not previous:
        return None
    embeddings = {
        int(cluster_id): list(embedding)
        for cluster_id, embedding in (
            await db.execute(
                select(NewsCluster.id, News.embedding)
                .join(News, News.id == NewsCluster.representative_news_id)
                .where(NewsCluster.id.in_(cluster_ids))
                .where(News.embedding.is_not(None))
            )
        ).all()
    }
    result: dict[str, dict[str, float]] = {}
    for current in today:
        current_embedding = embeddings.get(int(current["cluster_id"]))
        if current_embedding is None:
            continue
        result[str(current["issue_id"])] = {
            str(prior["issue_id"]): round(
                _cosine(
                    current_embedding,
                    embeddings[int(prior["cluster_id"])],
                ),
                4,
            )
            for prior in previous
            if int(prior["cluster_id"]) in embeddings
        }
    return result or None


async def load_daily_plan_candidates(
    db: AsyncSession,
    learning_date: date,
) -> list[tuple[LearningRole, LearningCandidate]] | None:
    """저장된 기본 계획을 position 순으로 ORM 후보와 함께 읽는다."""
    plan_id = (
        await db.execute(
            select(DailyLearningPlan.id).where(
                DailyLearningPlan.learning_date == learning_date
            )
        )
    ).scalar_one_or_none()
    if plan_id is None:
        return None
    rows = (
        await db.execute(
            select(
                DailyLearningPlanItem.role,
                IssueDocent,
                NewsCluster,
                NewsAnalysis,
            )
            .join(
                DailyLearningPlan,
                DailyLearningPlan.id == DailyLearningPlanItem.plan_id,
            )
            .join(
                IssueDocent,
                IssueDocent.id == DailyLearningPlanItem.issue_docent_id,
            )
            .join(NewsCluster, NewsCluster.id == IssueDocent.cluster_id)
            .join(NewsAnalysis, NewsAnalysis.cluster_id == NewsCluster.id)
            .where(DailyLearningPlan.id == plan_id)
            .order_by(DailyLearningPlanItem.position)
        )
    ).all()
    return [
        (
            cast(LearningRole, role),
            LearningCandidate(docent, cluster, analysis),
        )
        for role, docent, cluster, analysis in rows
    ]


async def run_daily_learning_planner(
    db: AsyncSession,
    *,
    learning_date: date | None = None,
    llm=None,
    candidates: list[LearningCandidate] | None = None,
) -> DailyLearningPlannerState:
    """당일 계획을 한 번만 생성하고 판정·선택을 한 트랜잭션으로 저장한다."""
    target_date = learning_date or now_kst().date()
    existing = (
        await db.execute(
            select(DailyLearningPlan).where(
                DailyLearningPlan.learning_date == target_date
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "learning_date": target_date.isoformat(),
            "candidates": existing.candidate_count,
            "selected": existing.item_count,
            "repair_attempted": existing.repair_attempted,
            "cached": True,
        }

    loaded = candidates if candidates is not None else await load_candidates(db)
    fresh_candidates = [
        candidate
        for candidate in loaded
        if getattr(candidate.cluster, "run_date", None) == target_date
    ]
    today_rows = [candidate_to_scoring_row(candidate) for candidate in fresh_candidates]
    previous = await _recent_selected_rows(db, target_date)
    compared_issue_ids = [int(row["issue_id"]) for row in previous]

    judgments = []
    repair_attempted = False
    chosen: list[tuple[str, dict]] = []
    if today_rows:
        judgments, repair_attempted = await judge_candidates(
            target_date.isoformat(),
            today_rows,
            previous,
            llm=llm,
        )
        judgment_by_id = {
            judgment.issue_id: judgment.model_dump() for judgment in judgments
        }
        chosen = select_daily_v4(
            today_rows,
            target_date.isoformat(),
            previous,
            await _similarities(db, today_rows, previous),
            judgment_by_id,
        )

    chosen_by_role = {role: row for role, row in chosen}
    ordered = [
        (role, chosen_by_role[role])
        for role in ROLE_ORDER
        if role in chosen_by_role
    ]
    plan = DailyLearningPlan(
        learning_date=target_date,
        selection_model=SELECTION_MODEL,
        prompt_version=JUDGE_PROMPT_VERSION,
        compared_issue_ids=compared_issue_ids,
        candidate_count=len(today_rows),
        item_count=len(ordered),
        repair_attempted=repair_attempted,
    )
    db.add(plan)
    await db.flush()
    db.add_all(
        [
            DailyLearningCandidateJudgment(
                plan_id=plan.id,
                issue_docent_id=judgment.issue_id,
                learn_value=judgment.learn_value,
                focus_fit=judgment.focus_fit,
                context_fit=judgment.context_fit,
                discovery_fit=judgment.discovery_fit,
                explains_why=judgment.explains_why,
                topic_overlap=judgment.topic_overlap,
                has_new_development=judgment.has_new_development,
                matched_previous_issue_ids=judgment.matched_previous_issue_ids,
                reason=judgment.reason,
                prompt_version=JUDGE_PROMPT_VERSION,
            )
            for judgment in judgments
        ]
    )
    db.add_all(
        [
            DailyLearningPlanItem(
                plan_id=plan.id,
                issue_docent_id=int(row["issue_id"]),
                role=role,
                position=position,
            )
            for position, (role, row) in enumerate(ordered, start=1)
        ]
    )
    await db.commit()
    return {
        "learning_date": target_date.isoformat(),
        "candidates": len(today_rows),
        "selected": len(ordered),
        "repair_attempted": repair_attempted,
        "cached": False,
    }
