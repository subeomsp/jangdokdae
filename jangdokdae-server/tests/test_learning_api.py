import os
from datetime import date, datetime
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.api.routers.learning import (
    _personalize_canonical_plan,
    _quiz_question,
    _role_copy,
    get_learning_archive,
    submit_daily_quiz,
)
from app.api.schemas.learning import DailyQuizSubmitRequest
from app.db.orm_models.issue_docent import IssueDocent
from services.learning_selection import LearningCandidate, select_daily_candidates


def _candidate(
    issue_id: int,
    *,
    importance: float,
    scope: str,
    sectors: list[int],
    companies: list[int] | None = None,
    run_date: date | None = None,
) -> LearningCandidate:
    return LearningCandidate(
        docent=SimpleNamespace(
            id=issue_id,
            title=f"이슈 {issue_id}",
            hook_lines={"neutral": f"이슈 {issue_id} 요약"},
            quizzes=_quizzes(),
            created_at=datetime(2026, 7, 31, 9, 0),
        ),
        cluster=SimpleNamespace(
            importance=importance,
            run_date=run_date,
            size=3,
        ),
        analysis=SimpleNamespace(
            scope=scope,
            sector_ids=sectors,
            company_ids=companies or [],
        ),
    )


def _quizzes() -> list[dict]:
    return [
        {
            "quiz_id": "quiz-1",
            "kind": "term",
            "question": "용어 문제",
            "options": ["a", "b", "c", "d"],
            "answer_index": 0,
            "explanation": "용어 설명",
        },
        {
            "quiz_id": "quiz-2",
            "kind": "issue",
            "question": "핵심 이슈는 무엇인가요?",
            "options": ["a", "b", "c", "d"],
            "answer_index": 1,
            "explanation": "핵심 설명",
        },
        {
            "quiz_id": "quiz-3",
            "kind": "domain",
            "question": "어디에 영향을 주나요?",
            "options": ["a", "b", "c", "d"],
            "answer_index": 2,
            "explanation": "영향 설명",
        },
    ]


def test_daily_selection_uses_interest_context_and_discovery_slots():
    candidates = [
        _candidate(4, importance=0.95, scope="회사", sectors=[3]),
        _candidate(2, importance=0.90, scope="시장 전체", sectors=[1]),
        _candidate(1, importance=0.80, scope="업종·테마", sectors=[1]),
        _candidate(3, importance=0.70, scope="회사", sectors=[2]),
    ]

    selected = select_daily_candidates(candidates, sector_ids={1}, company_ids=set())

    assert [(role, candidate.issue_id) for role, candidate in selected] == [
        ("focus", 1),
        ("context", 2),
        ("discovery", 4),
    ]


def test_daily_selection_falls_back_to_importance_without_interests():
    candidates = [
        _candidate(4, importance=0.95, scope="회사", sectors=[3]),
        _candidate(2, importance=0.90, scope="시장 전체", sectors=[1]),
        _candidate(3, importance=0.70, scope="회사", sectors=[2]),
    ]

    selected = select_daily_candidates(candidates, sector_ids=set(), company_ids=set())

    assert selected[0][1].issue_id == 4
    assert selected[1][1].issue_id == 2
    assert len({candidate.issue_id for _, candidate in selected}) == 3


def test_focus_copy_does_not_claim_personalization_for_fallback():
    assert _role_copy("focus", False) == (
        "오늘의 핵심",
        "오늘 가장 먼저 이해할 이슈예요",
    )


def test_personalization_never_adds_candidate_outside_v4_plan():
    canonical = [
        ("focus", _candidate(1, importance=0.9, scope="회사", sectors=[1])),
        ("context", _candidate(2, importance=0.8, scope="시장 전체", sectors=[2])),
        ("discovery", _candidate(3, importance=0.7, scope="회사", sectors=[3])),
    ]

    chosen = _personalize_canonical_plan(
        canonical,
        sector_ids={3},
        company_ids=set(),
    )

    assert chosen[0][1].issue_id == 3
    assert {candidate.issue_id for _, candidate in chosen} == {1, 2, 3}


@pytest.mark.asyncio
async def test_learning_archive_prefers_saved_plan_and_reconstructs_older_day(
    monkeypatch,
):
    from app.api.routers import learning

    monkeypatch.setattr(learning, "now_kst", lambda: datetime(2026, 8, 3, 10, 0))

    saved = [
        ("focus", _candidate(1, importance=0.9, scope="회사", sectors=[1])),
        ("context", _candidate(2, importance=0.8, scope="시장 전체", sectors=[2])),
    ]

    async def fake_saved_plan(_db, learning_date):
        return saved if learning_date == date(2026, 8, 2) else None

    async def fake_load(_db, as_of=None):
        day = as_of.date()
        return [
            _candidate(
                issue_id,
                importance=1 - issue_id / 100,
                scope="회사",
                sectors=[issue_id],
                run_date=day,
            )
            for issue_id in (3, 4, 5, 6)
        ]

    monkeypatch.setattr(learning, "load_daily_plan_candidates", fake_saved_plan)
    monkeypatch.setattr(learning, "_load_candidates", fake_load)

    response = await get_learning_archive(days=2, db=object())

    assert [row.learning_date for row in response.days] == [
        date(2026, 8, 2),
        date(2026, 8, 1),
    ]
    assert [item.id for item in response.days[0].items] == [1, 2]
    assert [item.id for item in response.days[1].items] == [3, 4, 5]


def test_daily_quiz_exposes_only_the_single_issue_question():
    response = _quiz_question(SimpleNamespace(quizzes=_quizzes()))

    assert response.quiz_id == "quiz-2"
    assert response.kind == "issue"
    assert "answer_index" not in response.model_dump()
    assert "explanation" not in response.model_dump()


@pytest.mark.asyncio
async def test_guest_daily_quiz_returns_feedback_without_db_write():
    db = _DocentDB(SimpleNamespace(id=9, quizzes=_quizzes()))

    response = await submit_daily_quiz(
        9,
        DailyQuizSubmitRequest(selected_index=1),
        db=db,
        user_id=None,
    )

    assert response.is_correct is True
    assert response.explanation == "핵심 설명"
    assert db.executed is False


def test_issue_docent_model_matches_normalized_database_shape():
    columns = IssueDocent.__table__.columns

    assert "sector_ids" not in columns
    assert "company_ids" not in columns
    assert "market_ids" not in columns


class _DocentDB:
    def __init__(self, docent):
        self.docent = docent
        self.executed = False

    async def get(self, _model, issue_id):
        return self.docent if issue_id == self.docent.id else None

    async def execute(self, _statement):
        self.executed = True

    async def commit(self):
        pass
