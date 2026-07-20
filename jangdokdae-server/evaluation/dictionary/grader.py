"""용어 분리 Outcome을 결정적으로 평가하는 코드 grader."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from evaluation.dictionary.schemas import SegmentationEvalTask
from services.analyzer.bok_dictionary import normalize_term
from services.analyzer.dictionary_segmentation import (
    TermUnitProposal,
    normalize_proposal,
    validate_term_unit_proposal,
)


class SegmentationGrade(BaseModel):
    """문서의 30/35/20/15 배점을 그대로 표현한 평가 결과."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    relationship_score: float = Field(ge=0, le=30)
    term_score: float = Field(ge=0, le=35)
    alias_score: float = Field(ge=0, le=20)
    source_support_score: float = Field(ge=0, le=15)
    total_score: float = Field(ge=0, le=100)
    passed: bool
    # 첫 baseline Transcript에는 필드가 없으므로 빈 기본값으로 하위 호환한다.
    mismatches: list[str] = Field(default_factory=list)
    hard_failures: list[str]


def _key(value: str) -> str:
    return normalize_term(value).casefold()


def _set_f1(expected: set[str], predicted: set[str]) -> float:
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    true_positives = len(expected & predicted)
    precision = true_positives / len(predicted)
    recall = true_positives / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _term_set(task: SegmentationEvalTask) -> set[str]:
    return {_key(unit.term) for unit in task.expected.units}


def _alias_pairs(task: SegmentationEvalTask) -> set[tuple[str, str]]:
    return {
        (_key(unit.term), _key(alias))
        for unit in task.expected.units
        for alias in unit.aliases
    }


def _predicted_term_set(proposal: TermUnitProposal) -> set[str]:
    return {_key(unit.term) for unit in proposal.units}


def _predicted_alias_pairs(proposal: TermUnitProposal) -> set[tuple[str, str]]:
    return {
        (_key(unit.term), _key(alias))
        for unit in proposal.units
        for alias in unit.aliases
    }


def grade_segmentation(
    task: SegmentationEvalTask,
    raw_prediction: TermUnitProposal,
    *,
    pass_threshold: float = 85,
) -> SegmentationGrade:
    """한 분리 결과를 골드 라벨 및 한국은행 원문과 비교한다."""

    prediction = normalize_proposal(raw_prediction)
    relationship_matches = prediction.relationship == task.expected.relationship
    expected_terms = _term_set(task)
    predicted_terms = _predicted_term_set(prediction)
    expected_aliases = _alias_pairs(task)
    predicted_aliases = _predicted_alias_pairs(prediction)
    term_f1 = _set_f1(expected_terms, predicted_terms)
    alias_f1 = _set_f1(expected_aliases, predicted_aliases)
    mismatches: list[str] = []
    if not relationship_matches:
        mismatches.append("relationship_mismatch")
    if expected_terms != predicted_terms:
        mismatches.append("term_set_mismatch")
    if expected_aliases != predicted_aliases:
        mismatches.append("alias_set_mismatch")

    validation_problems = validate_term_unit_proposal(
        task.source_term,
        task.raw_definition,
        prediction,
    )
    unsupported = [
        problem for problem in validation_problems if problem.startswith("unsupported_")
    ]
    hard_failures = list(validation_problems)

    if (
        task.expected.relationship == "notation"
        and prediction.relationship == "distinct_concepts"
    ):
        hard_failures.append("over_split_notation")
    if (
        task.expected.relationship == "distinct_concepts"
        and prediction.relationship in {"single", "aliases", "notation"}
    ):
        hard_failures.append("merged_distinct_concepts")

    # 같은 원인에서 나온 문자열을 한 번만 보고한다.
    hard_failures = list(dict.fromkeys(hard_failures))

    relationship_score = 30.0 if relationship_matches else 0.0
    term_score = 35.0 * term_f1
    alias_score = 20.0 * alias_f1
    source_support_score = 0.0 if unsupported else 15.0
    total_score = (
        relationship_score + term_score + alias_score + source_support_score
    )
    passed = total_score >= pass_threshold and not hard_failures

    return SegmentationGrade(
        task_id=task.id,
        relationship_score=round(relationship_score, 2),
        term_score=round(term_score, 2),
        alias_score=round(alias_score, 2),
        source_support_score=round(source_support_score, 2),
        total_score=round(total_score, 2),
        passed=passed,
        mismatches=mismatches,
        hard_failures=hard_failures,
    )
