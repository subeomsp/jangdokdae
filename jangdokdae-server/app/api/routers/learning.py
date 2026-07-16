"""하루 세 가지 이슈를 골라 읽기→퀴즈→완료로 잇는 MVP API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import QuizQuestionResponse
from app.api.routers.issues import build_issue_list_item
from app.api.schemas.learning import (
    DailyLearningItemResponse,
    DailyLearningResponse,
    DailyQuizSubmitRequest,
    DailyQuizSubmitResponse,
    LearningRole,
)
from app.core.security import get_current_user_optional
from app.db.base import KST_NOW, get_db
from app.db.orm_models.issue_docent import IssueDocent
from app.db.orm_models.news_analysis import NewsAnalysis
from app.db.orm_models.news_cluster import NewsCluster
from app.db.orm_models.user_issue_activity import UserIssueActivity
from app.db.queries import get_user_interests
from utils.dates import now_kst

router = APIRouter(prefix="/learning", tags=["learning"])

_CANDIDATE_WINDOW_DAYS = 7
_CANDIDATE_LIMIT = 60


@dataclass(frozen=True)
class LearningCandidate:
    docent: Any
    cluster: Any
    analysis: Any

    @property
    def issue_id(self) -> int:
        return int(self.docent.id)

    @property
    def importance(self) -> float:
        return float(getattr(self.cluster, "importance", 0.0) or 0.0)

    @property
    def sector_ids(self) -> set[int]:
        return {int(value) for value in (getattr(self.analysis, "sector_ids", None) or [])}

    @property
    def company_ids(self) -> set[int]:
        return {int(value) for value in (getattr(self.analysis, "company_ids", None) or [])}

    @property
    def is_market_context(self) -> bool:
        return str(getattr(self.analysis, "scope", "")) == "시장 전체"


def _matches_interests(
    candidate: LearningCandidate,
    sector_ids: set[int],
    company_ids: set[int],
) -> bool:
    return bool(candidate.sector_ids & sector_ids or candidate.company_ids & company_ids)


def _first_not_selected(
    candidates: list[LearningCandidate], selected: list[LearningCandidate]
) -> LearningCandidate | None:
    selected_ids = {candidate.issue_id for candidate in selected}
    return next(
        (candidate for candidate in candidates if candidate.issue_id not in selected_ids),
        None,
    )


def select_daily_candidates(
    candidates: list[LearningCandidate],
    *,
    sector_ids: set[int],
    company_ids: set[int],
) -> list[tuple[LearningRole, LearningCandidate]]:
    """최신·중요도순 후보를 관심→시장 맥락→관심 밖 발견의 최대 세 자리로 재배열한다."""
    if not candidates:
        return []

    # `_load_candidates`가 최신 실행일→중요도순으로 만든 순서를 유지한다. 여기서
    # 중요도만으로 다시 정렬하면 오래된 고득점 뉴스가 오늘 뉴스보다 앞설 수 있다.
    ranked = candidates
    selected: list[LearningCandidate] = []

    matching = [
        candidate
        for candidate in ranked
        if _matches_interests(candidate, sector_ids, company_ids)
    ]
    direct_matching = [candidate for candidate in matching if not candidate.is_market_context]
    focus = _first_not_selected(direct_matching or matching or ranked, selected)
    if focus is not None:
        selected.append(focus)

    context_matching = [
        candidate for candidate in matching if candidate.is_market_context
    ]
    all_context = [candidate for candidate in ranked if candidate.is_market_context]
    context = _first_not_selected(context_matching or all_context or ranked, selected)
    if context is not None:
        selected.append(context)

    non_matching = [
        candidate
        for candidate in ranked
        if not _matches_interests(candidate, sector_ids, company_ids)
    ]
    used_sectors = set().union(*(candidate.sector_ids for candidate in selected))
    diverse_non_matching = [
        candidate
        for candidate in non_matching
        if not candidate.sector_ids or candidate.sector_ids.isdisjoint(used_sectors)
    ]
    discovery = _first_not_selected(diverse_non_matching or non_matching or ranked, selected)
    if discovery is not None:
        selected.append(discovery)

    while len(selected) < min(3, len(ranked)):
        fallback = _first_not_selected(ranked, selected)
        if fallback is None:
            break
        selected.append(fallback)

    roles: list[LearningRole] = ["focus", "context", "discovery"]
    return list(zip(roles, selected, strict=False))


def _primary_quiz(docent: Any) -> dict[str, Any]:
    quizzes = list(getattr(docent, "quizzes", None) or [])
    quiz = next((item for item in quizzes if item.get("kind") == "issue"), None)
    if quiz is None:
        quiz = quizzes[0] if quizzes else None
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not ready")
    return quiz


def _quiz_question(docent: Any) -> QuizQuestionResponse:
    quiz = _primary_quiz(docent)
    return QuizQuestionResponse(
        quiz_id=str(quiz.get("quiz_id")),
        kind=str(quiz.get("kind")),
        question=str(quiz.get("question")),
        options=list(quiz.get("options") or []),
    )


def _role_copy(role: LearningRole, personalized: bool) -> tuple[str, str]:
    if role == "focus":
        if personalized:
            return "내 관심", "관심 분야에서 고른 오늘의 핵심이에요"
        return "오늘의 핵심", "오늘 가장 먼저 이해할 이슈예요"
    if role == "context":
        return "시장 맥락", "개별 뉴스 너머의 큰 흐름을 짚어요"
    return "시야 넓히기", "익숙한 관심사 밖의 중요한 흐름이에요"


async def _load_candidates(db: AsyncSession) -> list[LearningCandidate]:
    since = now_kst() - timedelta(days=_CANDIDATE_WINDOW_DAYS)
    rows = (
        await db.execute(
            select(IssueDocent, NewsCluster, NewsAnalysis)
            .join(NewsCluster, IssueDocent.cluster_id == NewsCluster.id)
            .join(NewsAnalysis, IssueDocent.cluster_id == NewsAnalysis.cluster_id)
            .where(IssueDocent.created_at >= since)
            .where(NewsAnalysis.is_investment_relevant.is_(True))
            .where(NewsAnalysis.needs_review.is_(False))
            .where(func.jsonb_array_length(IssueDocent.quizzes) > 0)
            .order_by(
                NewsCluster.run_date.desc(),
                NewsCluster.is_current.desc(),
                NewsCluster.importance.desc(),
                IssueDocent.created_at.desc(),
            )
            .limit(_CANDIDATE_LIMIT)
        )
    ).all()

    # 같은 stable cluster가 여러 실행일에 다시 생성됐으면 최신 콘텐츠 하나만 쓴다.
    deduplicated: list[LearningCandidate] = []
    seen: set[tuple[str, int]] = set()
    for docent, cluster, analysis in rows:
        stable_id = getattr(cluster, "stable_id", None)
        key = ("stable", int(stable_id)) if stable_id is not None else ("cluster", cluster.id)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(LearningCandidate(docent, cluster, analysis))
    return deduplicated


@router.get("/today", response_model=DailyLearningResponse)
async def get_today_learning(
    sector_ids: list[int] = Query(default=[]),
    company_ids: list[int] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_current_user_optional),
) -> DailyLearningResponse:
    requested_sector_ids = {value for value in sector_ids if value > 0}
    requested_company_ids = {value for value in company_ids if value > 0}
    if user_id is not None:
        interests = await get_user_interests(db, user_id)
        requested_sector_ids.update(interests["sector_ids"])
        requested_company_ids.update(interests["company_ids"])

    candidates = await _load_candidates(db)
    chosen = select_daily_candidates(
        candidates,
        sector_ids=requested_sector_ids,
        company_ids=requested_company_ids,
    )
    issue_ids = [candidate.issue_id for _, candidate in chosen]

    completed_ids: set[int] = set()
    if user_id is not None and issue_ids:
        completed_ids = set(
            (
                await db.execute(
                    select(UserIssueActivity.issue_docent_id)
                    .where(UserIssueActivity.user_id == user_id)
                    .where(UserIssueActivity.issue_docent_id.in_(issue_ids))
                    .where(UserIssueActivity.quiz_completed_at.is_not(None))
                )
            ).scalars().all()
        )

    personalized = bool(requested_sector_ids or requested_company_ids)
    items: list[DailyLearningItemResponse] = []
    for position, (role, candidate) in enumerate(chosen, start=1):
        matches_interest = _matches_interests(
            candidate,
            requested_sector_ids,
            requested_company_ids,
        )
        role_label, reason = _role_copy(role, personalized and matches_interest)
        items.append(
            DailyLearningItemResponse(
                position=position,
                role=role,
                role_label=role_label,
                reason=reason,
                issue=build_issue_list_item(
                    candidate.docent, candidate.cluster, candidate.analysis
                ),
                quiz=_quiz_question(candidate.docent),
                completed=candidate.issue_id in completed_ids,
            )
        )

    completed_count = sum(item.completed for item in items)
    return DailyLearningResponse(
        learning_date=now_kst().date(),
        items=items,
        completed_count=completed_count,
        total_count=len(items),
        is_complete=bool(items) and completed_count == len(items),
        personalized=personalized,
    )


@router.post("/today/{issue_id}/quiz", response_model=DailyQuizSubmitResponse)
async def submit_daily_quiz(
    issue_id: int,
    payload: DailyQuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_current_user_optional),
) -> DailyQuizSubmitResponse:
    docent = await db.get(IssueDocent, issue_id)
    if docent is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    quiz = _primary_quiz(docent)
    answer_index = int(quiz.get("answer_index"))
    quiz_id = str(quiz.get("quiz_id"))
    is_correct = payload.selected_index == answer_index

    if user_id is not None:
        result = {
            "quiz_id": quiz_id,
            "kind": str(quiz.get("kind")),
            "selected_index": payload.selected_index,
            "answer_index": answer_index,
            "is_correct": is_correct,
            "explanation": str(quiz.get("explanation") or ""),
        }
        values = {
            "read_at": KST_NOW,
            "quiz_answers": {quiz_id: payload.selected_index},
            "quiz_results": [result],
            "quiz_correct_count": int(is_correct),
            "quiz_total_count": 1,
            "quiz_completed_at": KST_NOW,
            "updated_at": KST_NOW,
        }
        await db.execute(
            pg_insert(UserIssueActivity)
            .values(user_id=user_id, issue_docent_id=issue_id, **values)
            .on_conflict_do_update(
                index_elements=["user_id", "issue_docent_id"],
                set_=values,
            )
        )
        await db.commit()

    return DailyQuizSubmitResponse(
        issue_id=issue_id,
        quiz_id=quiz_id,
        selected_index=payload.selected_index,
        answer_index=answer_index,
        is_correct=is_correct,
        explanation=str(quiz.get("explanation") or ""),
    )
