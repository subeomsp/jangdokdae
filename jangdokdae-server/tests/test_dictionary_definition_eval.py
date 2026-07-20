import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from evaluation.dictionary.definition_runner import (
    run_definition_trials,
    task_specific_problems,
)
from evaluation.dictionary.definition_schemas import load_definition_tasks
from scripts.export_dictionary_definition_gold import _task_from_rows
from services.analyzer.dictionary_generator import (
    DictionaryDraft,
    GroundedDictionaryAttempt,
    GroundedDictionaryResult,
    GroundingVerdict,
)

TASKS_PATH = (
    Path(__file__).parents[1]
    / "evaluation"
    / "dictionary"
    / "tasks"
    / "definition_gold.jsonl"
)


def test_approved_definition_becomes_gold_task():
    source_term = "간접금융/직접금융"
    raw_definition = "간접금융은 금융기관이 자금을 중개하는 방식이며 직접금융과 구분된다."
    source = SimpleNamespace(
        source_version="2024",
        source_page=5,
        pdf_page=23,
        term=source_term,
        raw_definition=raw_definition,
        content_hash=hashlib.sha256(
            f"{source_term}\n{raw_definition}".encode()
        ).hexdigest(),
    )
    row = SimpleNamespace(
        status="approved",
        source="bok_800",
        verification_status="verified",
        quality_score=95,
        source_unit_index=0,
        term="간접금융",
        aliases=["Indirect Financing"],
        term_type="finance",
        definition="간접금융은 금융기관이 자금의 공급자와 수요자 사이를 중개하는 방식입니다.",
        example=None,
    )

    task = _task_from_rows(
        row,
        source,
        task_id="bok-def-001",
        reviewed_at=datetime(2026, 7, 20, 21, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert task.term == "간접금융"
    assert task.reference.definition == row.definition
    assert task.content_hash == source.content_hash


def test_definition_goldset_contains_five_approved_tasks():
    tasks = load_definition_tasks(TASKS_PATH)

    assert len(tasks) == 5
    assert {task.term for task in tasks} == {
        "간접금융",
        "직접금융",
        "경기조절정책",
        "경제활동인구",
        "비경제활동인구",
    }


@pytest.mark.asyncio
async def test_definition_runner_calculates_pass_at_1_and_pass_power_3():
    task = load_definition_tasks(TASKS_PATH)[0]

    async def pipeline(_term, _raw_definition):
        draft = DictionaryDraft(
            term_type="finance",
            definition=task.reference.definition,
            example=task.reference.example,
        )
        verdict = GroundingVerdict(
            supported=True,
            score=95,
            reason="원문 근거와 가독성 기준을 통과했습니다.",
        )
        return GroundedDictionaryResult(
            attempts=[
                GroundedDictionaryAttempt(
                    attempt_number=1,
                    latency_ms=10,
                    draft=draft,
                    deterministic_problems=[],
                    verdict=verdict,
                )
            ]
        )

    run = await run_definition_trials(
        [task],
        repeats=3,
        pipeline=pipeline,
    )

    assert run.metrics.pass_at_1 == 1
    assert run.metrics.pass_power_k == 1
    assert run.metrics.passed_trial_count == 3
    assert run.metrics.generation_attempt_count == 3
    assert run.metrics.retried_trial_count == 0


def test_definition_task_specific_checks_catch_known_regressions():
    task = load_definition_tasks(TASKS_PATH)[2]
    draft = DictionaryDraft(
        term_type="finance",
        definition="경기조절정책은 정부가 재정지출과 세금을 조절하는 정책입니다.",
        example=None,
    )

    assert task_specific_problems(task, draft) == [
        "missing_required_concept_group:0"
    ]
