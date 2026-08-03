"""하루 세 가지 이슈를 골라 읽기→퀴즈→완료로 잇는 MVP API."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import QuizQuestionResponse
from app.api.routers.issues import build_issue_list_item
from app.api.schemas.learning import (
    DailyLearningItemResponse,
    DailyLearningResponse,
    DailyQuizSubmitRequest,
    DailyQuizSubmitResponse,
    LearningArchiveDayResponse,
    LearningArchiveResponse,
    LearningRole,
)
from app.core.security import get_current_user_optional
from app.db.base import KST_NOW, get_db
from app.db.orm_models.issue_docent import IssueDocent
from app.db.orm_models.user_issue_activity import UserIssueActivity
from app.db.queries import get_user_interests
from services.learning_selection import (
    LearningCandidate,
    select_daily_candidates,
)
from services.learning_selection import (
    load_candidates as _load_candidates,
)
from services.learning_selection import (
    matches_interests as _matches_interests,
)
from services.pipeline.daily_learning_planner import load_daily_plan_candidates
from utils.dates import now_kst

router = APIRouter(prefix="/learning", tags=["learning"])


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


def _personalize_canonical_plan(
    canonical_plan: list[tuple[LearningRole, LearningCandidate]],
    *,
    sector_ids: set[int],
    company_ids: set[int],
) -> list[tuple[LearningRole, LearningCandidate]]:
    """v4 승인 집합을 유지한 채 관심사가 있으면 기존 세 자리 규칙으로 재배열한다."""
    if not sector_ids and not company_ids:
        return canonical_plan
    return select_daily_candidates(
        [candidate for _, candidate in canonical_plan],
        sector_ids=sector_ids,
        company_ids=company_ids,
    )


@router.get("/archive", response_model=LearningArchiveResponse)
async def get_learning_archive(
    days: int = Query(default=14, ge=1, le=14),
    db: AsyncSession = Depends(get_db),
) -> LearningArchiveResponse:
    """오늘을 제외한 최근 학습일의 기본 계획을 날짜별로 반환한다."""
    today = now_kst().date()
    archive_days: list[LearningArchiveDayResponse] = []
    for days_ago in range(1, days + 1):
        learning_date = today - timedelta(days=days_ago)
        canonical_plan = await load_daily_plan_candidates(db, learning_date)

        # v4 계획 저장 기능 도입 전 날짜는 그날 생성된 후보로 최소한 재구성한다.
        if canonical_plan is None:
            end_of_day = datetime.combine(learning_date, time.max)
            candidates = await _load_candidates(db, as_of=end_of_day)
            fresh = [
                candidate
                for candidate in candidates
                if getattr(candidate.cluster, "run_date", None) == learning_date
            ]
            canonical_plan = select_daily_candidates(
                fresh,
                sector_ids=set(),
                company_ids=set(),
            )

        if not canonical_plan:
            continue
        archive_days.append(
            LearningArchiveDayResponse(
                learning_date=learning_date,
                items=[
                    build_issue_list_item(
                        candidate.docent, candidate.cluster, candidate.analysis
                    )
                    for _, candidate in canonical_plan
                ],
            )
        )
    return LearningArchiveResponse(days=archive_days)


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

    learning_date = now_kst().date()
    canonical_plan = await load_daily_plan_candidates(db, learning_date)
    if canonical_plan is None:
        # 마이그레이션 직후 첫 파이프라인 실행 전에는 기존 휴리스틱으로 서비스 연속성을
        # 유지한다. 계획이 0건으로 저장된 날([])은 빈 계획을 그대로 존중한다.
        candidates = await _load_candidates(db)
        chosen = select_daily_candidates(
            candidates,
            sector_ids=requested_sector_ids,
            company_ids=requested_company_ids,
        )
    else:
        # 개인화는 v4가 승인한 기본 계획 안에서만 순서를 조정한다. 판정에서 탈락한
        # 후보를 관심사 때문에 다시 끌어올리지 않는다.
        chosen = _personalize_canonical_plan(
            canonical_plan,
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
        learning_date=learning_date,
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
