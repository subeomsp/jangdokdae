"""승인 골드셋에 분리 제안기를 반복 실행하고 Trial을 기록한다."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from evaluation.dictionary.grader import SegmentationGrade, grade_segmentation
from evaluation.dictionary.schemas import SegmentationEvalTask
from services.analyzer.dictionary_generator import grounded_dictionary_model_name
from services.analyzer.dictionary_segmentation import (
    SEGMENTATION_PROMPT_VERSION,
    TermRelationship,
    TermUnitProposal,
    propose_term_units,
)

SegmentationProposer = Callable[[str, str], Awaitable[TermUnitProposal]]


class SegmentationTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    source_term: str
    expected_relationship: TermRelationship
    trial_number: int = Field(ge=1)
    started_at: datetime
    latency_ms: int = Field(ge=0)
    prediction: TermUnitProposal | None
    grade: SegmentationGrade | None
    error: str | None


class RelationshipRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship: TermRelationship
    task_count: int = Field(ge=1)
    trial_count: int = Field(ge=1)
    trial_pass_rate: float = Field(ge=0, le=1)
    pass_at_1: float = Field(ge=0, le=1)
    pass_power_k: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=100)


class SegmentationRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int = Field(ge=1)
    trial_count: int = Field(ge=1)
    passed_trial_count: int = Field(ge=0)
    errored_trial_count: int = Field(ge=0)
    hard_failure_count: int = Field(ge=0)
    pass_at_1: float = Field(ge=0, le=1)
    pass_power_k: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=100)
    by_relationship: list[RelationshipRunSummary]


class SegmentationEvalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    completed_at: datetime
    model_name: str
    prompt_version: str
    repeats: int = Field(ge=1)
    task_content_hashes: dict[str, str]
    trials: list[SegmentationTrial]
    metrics: SegmentationRunMetrics


def _passed(trial: SegmentationTrial) -> bool:
    return bool(trial.grade and trial.grade.passed)


def _score(trial: SegmentationTrial) -> float:
    return trial.grade.total_score if trial.grade else 0.0


def _summarize_group(
    relationship: TermRelationship,
    task_ids: set[str],
    trials: list[SegmentationTrial],
    repeats: int,
) -> RelationshipRunSummary:
    first_trials = [trial for trial in trials if trial.trial_number == 1]
    trials_by_task: dict[str, list[SegmentationTrial]] = defaultdict(list)
    for trial in trials:
        trials_by_task[trial.task_id].append(trial)
    power_passes = sum(
        len(trials_by_task[task_id]) == repeats
        and all(_passed(trial) for trial in trials_by_task[task_id])
        for task_id in task_ids
    )
    return RelationshipRunSummary(
        relationship=relationship,
        task_count=len(task_ids),
        trial_count=len(trials),
        trial_pass_rate=round(sum(_passed(trial) for trial in trials) / len(trials), 4),
        pass_at_1=round(
            sum(_passed(trial) for trial in first_trials) / len(first_trials),
            4,
        ),
        pass_power_k=round(power_passes / len(task_ids), 4),
        average_score=round(sum(_score(trial) for trial in trials) / len(trials), 2),
    )


def build_run_metrics(
    tasks: list[SegmentationEvalTask],
    trials: list[SegmentationTrial],
    repeats: int,
) -> SegmentationRunMetrics:
    """Trial에서 운영 주지표 pass@1과 안정성 지표 pass^k를 계산한다."""

    expected_trials = len(tasks) * repeats
    if len(trials) != expected_trials:
        raise ValueError(f"expected {expected_trials} trials, got {len(trials)}")

    trials_by_task: dict[str, list[SegmentationTrial]] = defaultdict(list)
    for trial in trials:
        trials_by_task[trial.task_id].append(trial)

    first_trials = [trial for trial in trials if trial.trial_number == 1]
    power_passes = sum(
        len(trials_by_task[task.id]) == repeats
        and all(_passed(trial) for trial in trials_by_task[task.id])
        for task in tasks
    )

    relationships: dict[TermRelationship, set[str]] = defaultdict(set)
    for task in tasks:
        relationships[task.expected.relationship].add(task.id)
    relationship_order: tuple[TermRelationship, ...] = (
        "distinct_concepts",
        "aliases",
        "notation",
        "single",
    )
    by_relationship = []
    for relationship in relationship_order:
        task_ids = relationships[relationship]
        if not task_ids:
            continue
        relationship_trials = [
            trial for trial in trials if trial.task_id in task_ids
        ]
        by_relationship.append(
            _summarize_group(
                relationship,
                task_ids,
                relationship_trials,
                repeats,
            )
        )

    return SegmentationRunMetrics(
        task_count=len(tasks),
        trial_count=len(trials),
        passed_trial_count=sum(_passed(trial) for trial in trials),
        errored_trial_count=sum(trial.error is not None for trial in trials),
        hard_failure_count=sum(
            bool(trial.grade and trial.grade.hard_failures) for trial in trials
        ),
        pass_at_1=round(sum(_passed(trial) for trial in first_trials) / len(tasks), 4),
        pass_power_k=round(power_passes / len(tasks), 4),
        average_score=round(sum(_score(trial) for trial in trials) / len(trials), 2),
        by_relationship=by_relationship,
    )


async def run_segmentation_trials(
    tasks: list[SegmentationEvalTask],
    *,
    repeats: int = 3,
    proposer: SegmentationProposer = propose_term_units,
) -> SegmentationEvalRun:
    """DB를 수정하지 않고 각 Task를 독립적으로 반복 실행한다."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if any(task.label_status != "approved" for task in tasks):
        raise ValueError("live evaluation requires approved tasks")

    run_started_at = datetime.now(timezone.utc)
    trials: list[SegmentationTrial] = []
    for task in tasks:
        for trial_number in range(1, repeats + 1):
            started_at = datetime.now(timezone.utc)
            started_timer = perf_counter()
            prediction: TermUnitProposal | None = None
            grade: SegmentationGrade | None = None
            error: str | None = None
            try:
                prediction = await proposer(task.source_term, task.raw_definition)
                grade = grade_segmentation(task, prediction)
            except Exception as exc:  # 개별 실패도 전체 평가 Transcript에 남긴다.
                error = f"{type(exc).__name__}: {exc}"

            trials.append(
                SegmentationTrial(
                    task_id=task.id,
                    source_term=task.source_term,
                    expected_relationship=task.expected.relationship,
                    trial_number=trial_number,
                    started_at=started_at,
                    latency_ms=round((perf_counter() - started_timer) * 1000),
                    prediction=prediction,
                    grade=grade,
                    error=error,
                )
            )

    return SegmentationEvalRun(
        started_at=run_started_at,
        completed_at=datetime.now(timezone.utc),
        model_name=grounded_dictionary_model_name(),
        prompt_version=SEGMENTATION_PROMPT_VERSION,
        repeats=repeats,
        task_content_hashes={task.id: task.content_hash for task in tasks},
        trials=trials,
        metrics=build_run_metrics(tasks, trials, repeats),
    )
