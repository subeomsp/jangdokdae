"""용어 분리 코드 grader 결과 집계."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from evaluation.dictionary.grader import SegmentationGrade
from evaluation.dictionary.runner import SegmentationEvalRun
from evaluation.dictionary.schemas import SegmentationEvalTask
from services.analyzer.dictionary_segmentation import TermRelationship


class RelationshipSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship: TermRelationship
    task_count: int = Field(ge=1)
    passed_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=100)


class SegmentationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int = Field(ge=1)
    passed_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=100)
    hard_failure_count: int = Field(ge=0)
    by_relationship: list[RelationshipSummary]


def _average(values: list[float]) -> float:
    return sum(values) / len(values)


def build_segmentation_report(
    tasks: list[SegmentationEvalTask],
    grades: list[SegmentationGrade],
) -> SegmentationReport:
    """Task당 한 Trial의 결과를 전체 및 관계별로 집계한다."""

    task_by_id = {task.id: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("duplicate task ids")

    grade_by_id = {grade.task_id: grade for grade in grades}
    if len(grade_by_id) != len(grades):
        raise ValueError("duplicate grades for one or more tasks")
    if set(grade_by_id) != set(task_by_id):
        missing = sorted(set(task_by_id) - set(grade_by_id))
        unexpected = sorted(set(grade_by_id) - set(task_by_id))
        raise ValueError(f"task/grade mismatch: missing={missing}, unexpected={unexpected}")

    grouped: dict[TermRelationship, list[SegmentationGrade]] = defaultdict(list)
    for task_id, grade in grade_by_id.items():
        grouped[task_by_id[task_id].expected.relationship].append(grade)

    relationship_order: tuple[TermRelationship, ...] = (
        "distinct_concepts",
        "aliases",
        "notation",
        "single",
    )
    by_relationship = [
        RelationshipSummary(
            relationship=relationship,
            task_count=len(grouped[relationship]),
            passed_count=sum(grade.passed for grade in grouped[relationship]),
            pass_rate=round(
                sum(grade.passed for grade in grouped[relationship])
                / len(grouped[relationship]),
                4,
            ),
            average_score=round(
                _average([grade.total_score for grade in grouped[relationship]]),
                2,
            ),
        )
        for relationship in relationship_order
        if grouped[relationship]
    ]

    return SegmentationReport(
        task_count=len(grades),
        passed_count=sum(grade.passed for grade in grades),
        pass_rate=round(sum(grade.passed for grade in grades) / len(grades), 4),
        average_score=round(_average([grade.total_score for grade in grades]), 2),
        hard_failure_count=sum(bool(grade.hard_failures) for grade in grades),
        by_relationship=by_relationship,
    )


def render_run_markdown(run: SegmentationEvalRun) -> str:
    """사람이 빠르게 실패 유형을 검토할 수 있는 Markdown 리포트를 만든다."""

    metrics = run.metrics
    power_label = f"pass^{run.repeats}"
    lines = [
        "# 한국은행 용어 분리 에이전트 평가 결과",
        "",
        "## 요약",
        "",
        f"- 모델: `{run.model_name}`",
        f"- 프롬프트 버전: `{run.prompt_version}`",
        f"- 실행 시각(UTC): `{run.started_at.isoformat()}`",
        f"- Task: {metrics.task_count}개 × {run.repeats}회 = {metrics.trial_count} Trials",
        f"- `pass@1`: {metrics.pass_at_1:.1%}",
        f"- `{power_label}`: {metrics.pass_power_k:.1%}",
        f"- 전체 Trial 통과: {metrics.passed_trial_count}/{metrics.trial_count}",
        f"- 평균 점수: {metrics.average_score:.2f}",
        f"- 즉시 실패: {metrics.hard_failure_count}건",
        f"- 실행 오류: {metrics.errored_trial_count}건",
        "",
        "## 관계별 결과",
        "",
        f"| 관계 | Task | Trial 통과율 | pass@1 | {power_label} | 평균 점수 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in metrics.by_relationship:
        lines.append(
            f"| `{summary.relationship}` | {summary.task_count} "
            f"| {summary.trial_pass_rate:.1%} | {summary.pass_at_1:.1%} "
            f"| {summary.pass_power_k:.1%} | {summary.average_score:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Trial 상세",
            "",
            "| Task | 원문 제목 | Trial | 기대/예측 관계 | 점수 | 통과 | 지연 | 실패 원인 |",
            "| --- | --- | ---: | --- | ---: | --- | ---: | --- |",
        ]
    )
    for trial in run.trials:
        predicted_relationship = (
            trial.prediction.relationship if trial.prediction else "-"
        )
        score = f"{trial.grade.total_score:.2f}" if trial.grade else "0.00"
        passed = "PASS" if trial.grade and trial.grade.passed else "FAIL"
        failures = (
            ", ".join(trial.grade.hard_failures)
            if trial.grade and trial.grade.hard_failures
            else (
                ", ".join(trial.grade.mismatches)
                if trial.grade and trial.grade.mismatches
                else trial.error or "-"
            )
        )
        lines.append(
            f"| `{trial.task_id}` | {trial.source_term} | {trial.trial_number} "
            f"| `{trial.expected_relationship}` / `{predicted_relationship}` "
            f"| {score} | {passed} | {trial.latency_ms}ms | {failures} |"
        )

    gate_passed = (
        metrics.pass_at_1 == 1
        and metrics.pass_power_k == 1
        and metrics.hard_failure_count == 0
        and metrics.errored_trial_count == 0
    )
    lines.extend(
        [
            "",
            "## 현재 게이트 판정",
            "",
            (
                "**PASS** — 소형 회귀 게이트를 통과했습니다. 자동 승인 전에는 "
                "골드셋을 24개까지 확장해야 합니다."
                if gate_passed
                else "**HOLD** — 실패 사례를 수정하고 다시 평가해야 합니다."
            ),
            "",
        ]
    )
    return "\n".join(lines)
