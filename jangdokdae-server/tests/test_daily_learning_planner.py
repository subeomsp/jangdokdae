from datetime import date
from types import SimpleNamespace

import pytest

from app.db.orm_models.daily_learning_plan import (
    DailyLearningCandidateJudgment,
    DailyLearningPlan,
    DailyLearningPlanItem,
)
from services.learning_editorial import DayJudgmentV4
from services.learning_selection import LearningCandidate
from services.pipeline.daily_learning_planner import run_daily_learning_planner


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def all(self):
        return self.rows


class _DB:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        plan = next(item for item in self.added if isinstance(item, DailyLearningPlan))
        plan.id = 41

    async def commit(self):
        self.committed = True


class _LLM:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def ainvoke(self, _prompt):
        self.calls += 1
        return self.result


def _candidate(
    issue_id: int,
    *,
    scope: str,
    frame: str,
    sectors: list[int],
) -> LearningCandidate:
    return LearningCandidate(
        docent=SimpleNamespace(
            id=issue_id,
            title=f"이슈 {issue_id}",
            hook_lines={"neutral": f"훅 {issue_id}"},
        ),
        cluster=SimpleNamespace(
            id=100 + issue_id,
            stable_id=issue_id,
            run_date=date(2026, 7, 28),
            importance=0.5,
            size=5,
        ),
        analysis=SimpleNamespace(
            scope=scope,
            frame=frame,
            sector_ids=sectors,
            company_ids=[],
        ),
        source_count=3,
        sector_names=tuple(str(value) for value in sectors),
    )


def _judgment(
    issue_id: int,
    *,
    focus: int,
    context: int,
    discovery: int,
    explains_why: bool,
) -> dict:
    return {
        "issue_id": issue_id,
        "learn_value": 8,
        "focus_fit": focus,
        "context_fit": context,
        "discovery_fit": discovery,
        "explains_why": explains_why,
        "topic_overlap": False,
        "has_new_development": True,
        "matched_previous_issue_ids": [],
        "reason": "판정 근거",
    }


@pytest.mark.asyncio
async def test_planner_persists_verified_plan_and_all_candidate_judgments():
    candidates = [
        _candidate(1, scope="시장 전체", frame="TREND", sectors=[1]),
        _candidate(2, scope="회사", frame="EARNINGS", sectors=[2]),
        _candidate(3, scope="회사", frame="EARNINGS", sectors=[3]),
    ]
    llm = _LLM(
        DayJudgmentV4.model_validate(
            {
                "judgments": [
                    _judgment(
                        1,
                        focus=3,
                        context=10,
                        discovery=3,
                        explains_why=False,
                    ),
                    _judgment(
                        2,
                        focus=10,
                        context=2,
                        discovery=4,
                        explains_why=False,
                    ),
                    _judgment(
                        3,
                        focus=2,
                        context=2,
                        discovery=10,
                        explains_why=False,
                    ),
                ]
            }
        )
    )
    # 기존 계획 없음 → 최근 7일 계획 없음. previous가 비어 similarity 쿼리는 없다.
    db = _DB([_Result(scalar=None), _Result(rows=[])])

    state = await run_daily_learning_planner(
        db,
        learning_date=date(2026, 7, 28),
        llm=llm,
        candidates=candidates,
    )

    assert state == {
        "learning_date": "2026-07-28",
        "candidates": 3,
        "selected": 2,
        "repair_attempted": False,
        "cached": False,
    }
    assert llm.calls == 1
    assert db.committed is True
    assert len(
        [item for item in db.added if isinstance(item, DailyLearningCandidateJudgment)]
    ) == 3
    items = [item for item in db.added if isinstance(item, DailyLearningPlanItem)]
    assert [(item.position, item.role, item.issue_docent_id) for item in items] == [
        (1, "focus", 2),
        (2, "context", 1),
    ]


@pytest.mark.asyncio
async def test_planner_reuses_existing_daily_plan_without_llm_call():
    existing = DailyLearningPlan(
        id=7,
        learning_date=date(2026, 7, 28),
        selection_model="v4",
        prompt_version="selection-judge-v2.1",
        compared_issue_ids=[],
        candidate_count=12,
        item_count=3,
        repair_attempted=True,
    )
    db = _DB([_Result(scalar=existing)])
    llm = _LLM(None)

    state = await run_daily_learning_planner(
        db,
        learning_date=date(2026, 7, 28),
        llm=llm,
        candidates=[],
    )

    assert state["cached"] is True
    assert state["selected"] == 3
    assert state["repair_attempted"] is True
    assert llm.calls == 0
    assert db.committed is False
