"""승인 설명 골드셋에 생성·검증 파이프라인을 반복 실행한다."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from evaluation.dictionary.definition_schemas import DefinitionEvalTask
from services.analyzer.dictionary_generator import (
    GROUNDED_DICTIONARY_MIN_SCORE,
    GROUNDED_DICTIONARY_PROMPT_VERSION,
    DictionaryDraft,
    GroundedDictionaryAttempt,
    GroundedDictionaryResult,
    GroundingVerdict,
    generate_verified_grounded_dictionary_draft,
    grounded_dictionary_model_name,
)

DefinitionPipeline = Callable[
    [str, str],
    Awaitable[GroundedDictionaryResult],
]


def task_specific_problems(
    task: DefinitionEvalTask,
    draft: DictionaryDraft,
) -> list[str]:
    """사람이 골드 Task에 지정한 핵심 범위와 회귀 금지 표현을 검사한다."""

    text = f"{draft.definition} {draft.example or ''}".casefold()
    problems: list[str] = []
    for index, alternatives in enumerate(task.required_concept_groups):
        if not any(alternative.casefold() in text for alternative in alternatives):
            problems.append(f"missing_required_concept_group:{index}")
    for phrase in task.forbidden_phrases:
        if phrase.casefold() in text:
            problems.append(f"forbidden_phrase:{phrase}")
    return problems


class DefinitionTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    term: str
    trial_number: int = Field(ge=1)
    started_at: datetime
    latency_ms: int = Field(ge=0)
    attempts: list[GroundedDictionaryAttempt]
    draft: DictionaryDraft | None
    deterministic_problems: list[str]
    verdict: GroundingVerdict | None
    passed: bool
    error: str | None


class DefinitionRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int = Field(ge=1)
    trial_count: int = Field(ge=1)
    generation_attempt_count: int = Field(ge=0)
    retried_trial_count: int = Field(ge=0)
    passed_trial_count: int = Field(ge=0)
    errored_trial_count: int = Field(ge=0)
    deterministic_failure_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    pass_at_1: float = Field(ge=0, le=1)
    pass_power_k: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=100)


class DefinitionEvalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    completed_at: datetime
    model_name: str
    prompt_version: str
    minimum_score: int = Field(ge=0, le=100)
    repeats: int = Field(ge=1)
    task_content_hashes: dict[str, str]
    trials: list[DefinitionTrial]
    metrics: DefinitionRunMetrics


def build_definition_metrics(
    tasks: list[DefinitionEvalTask],
    trials: list[DefinitionTrial],
    repeats: int,
) -> DefinitionRunMetrics:
    expected_trials = len(tasks) * repeats
    if len(trials) != expected_trials:
        raise ValueError(f"expected {expected_trials} trials, got {len(trials)}")
    by_task: dict[str, list[DefinitionTrial]] = defaultdict(list)
    for trial in trials:
        by_task[trial.task_id].append(trial)
    first_trials = [trial for trial in trials if trial.trial_number == 1]
    power_passes = sum(
        len(by_task[task.id]) == repeats
        and all(trial.passed for trial in by_task[task.id])
        for task in tasks
    )
    scores = [trial.verdict.score if trial.verdict else 0 for trial in trials]
    return DefinitionRunMetrics(
        task_count=len(tasks),
        trial_count=len(trials),
        generation_attempt_count=sum(len(trial.attempts) for trial in trials),
        retried_trial_count=sum(len(trial.attempts) > 1 for trial in trials),
        passed_trial_count=sum(trial.passed for trial in trials),
        errored_trial_count=sum(trial.error is not None for trial in trials),
        deterministic_failure_count=sum(
            bool(trial.deterministic_problems) for trial in trials
        ),
        unsupported_count=sum(
            bool(trial.verdict and not trial.verdict.supported) for trial in trials
        ),
        pass_at_1=round(sum(trial.passed for trial in first_trials) / len(tasks), 4),
        pass_power_k=round(power_passes / len(tasks), 4),
        average_score=round(sum(scores) / len(scores), 2),
    )


async def run_definition_trials(
    tasks: list[DefinitionEvalTask],
    *,
    repeats: int = 3,
    pipeline: DefinitionPipeline = generate_verified_grounded_dictionary_draft,
) -> DefinitionEvalRun:
    """DB를 수정하지 않고 설명 생성과 별도 검증을 반복 실행한다."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    run_started_at = datetime.now(timezone.utc)
    trials: list[DefinitionTrial] = []
    for task in tasks:
        for trial_number in range(1, repeats + 1):
            started_at = datetime.now(timezone.utc)
            timer = perf_counter()
            draft: DictionaryDraft | None = None
            verdict: GroundingVerdict | None = None
            attempts: list[GroundedDictionaryAttempt] = []
            deterministic_problems: list[str] = []
            error: str | None = None
            passed = False
            try:
                result = await pipeline(task.term, task.raw_definition)
                attempts = result.attempts
                final_attempt = result.final_attempt
                draft = final_attempt.draft
                verdict = final_attempt.verdict
                deterministic_problems = list(final_attempt.deterministic_problems)
                deterministic_problems.extend(task_specific_problems(task, draft))
                passed = (
                    not deterministic_problems
                    and verdict.supported
                    and verdict.score >= GROUNDED_DICTIONARY_MIN_SCORE
                )
            except Exception as exc:  # 개별 오류도 나머지 Trial과 함께 기록한다.
                error = f"{type(exc).__name__}: {exc}"
            trials.append(
                DefinitionTrial(
                    task_id=task.id,
                    term=task.term,
                    trial_number=trial_number,
                    started_at=started_at,
                    latency_ms=round((perf_counter() - timer) * 1000),
                    attempts=attempts,
                    draft=draft,
                    deterministic_problems=deterministic_problems,
                    verdict=verdict,
                    passed=passed,
                    error=error,
                )
            )

    return DefinitionEvalRun(
        started_at=run_started_at,
        completed_at=datetime.now(timezone.utc),
        model_name=grounded_dictionary_model_name(),
        prompt_version=GROUNDED_DICTIONARY_PROMPT_VERSION,
        minimum_score=GROUNDED_DICTIONARY_MIN_SCORE,
        repeats=repeats,
        task_content_hashes={task.id: task.content_hash for task in tasks},
        trials=trials,
        metrics=build_definition_metrics(tasks, trials, repeats),
    )
