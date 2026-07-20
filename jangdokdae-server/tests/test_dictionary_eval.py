from pathlib import Path

import pytest

from evaluation.dictionary.grader import grade_segmentation
from evaluation.dictionary.report import build_segmentation_report
from evaluation.dictionary.runner import run_segmentation_trials
from evaluation.dictionary.schemas import load_segmentation_tasks
from services.analyzer.dictionary_segmentation import ProposedTermUnit, TermUnitProposal

TASKS_PATH = (
    Path(__file__).parents[1]
    / "evaluation"
    / "dictionary"
    / "tasks"
    / "segmentation_gold.jsonl"
)


def _load_tasks():
    return load_segmentation_tasks(TASKS_PATH)


def test_approved_eval_tasks_are_valid_and_cover_all_relationships():
    tasks = _load_tasks()

    assert len(tasks) == 13
    assert all(task.label_status == "approved" for task in tasks)
    assert {task.expected.relationship for task in tasks} == {
        "single",
        "distinct_concepts",
        "aliases",
        "notation",
    }


def test_draft_eval_tasks_are_rejected_by_default(tmp_path):
    approved_task = _load_tasks()[0]
    draft_task = approved_task.model_copy(
        update={
            "label_status": "draft",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    draft_path = tmp_path / "draft.jsonl"
    draft_path.write_text(draft_task.model_dump_json() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="draft labels are not an approved goldset"):
        load_segmentation_tasks(draft_path)


def _exact_grade(task):
    prediction = TermUnitProposal(
        relationship=task.expected.relationship,
        units=[
            ProposedTermUnit(term=unit.term, aliases=unit.aliases)
            for unit in task.expected.units
        ],
        reason="평가용 정답 예측",
    )
    return grade_segmentation(task, prediction)


def test_exact_predictions_score_100():
    for task in _load_tasks():
        grade = _exact_grade(task)

        assert grade.total_score == 100, task.id
        assert grade.passed is True, task.id
        assert grade.mismatches == [], task.id
        assert grade.hard_failures == [], task.id


def test_report_summarizes_overall_and_each_relationship():
    tasks = _load_tasks()
    report = build_segmentation_report(tasks, [_exact_grade(task) for task in tasks])

    assert report.task_count == 13
    assert report.passed_count == 13
    assert report.pass_rate == 1
    assert report.average_score == 100
    assert report.hard_failure_count == 0
    assert {
        summary.relationship: summary.task_count for summary in report.by_relationship
    } == {
        "distinct_concepts": 7,
        "aliases": 3,
        "notation": 2,
        "single": 1,
    }


def test_unsupported_alias_is_a_hard_failure():
    task = _load_tasks()[2]
    prediction = TermUnitProposal(
        relationship="aliases",
        units=[
            ProposedTermUnit(
                term="환매조건부매매",
                aliases=["RP", "Repo", "MADE-UP"],
            )
        ],
        reason="평가용 오류 예측",
    )

    grade = grade_segmentation(task, prediction)

    assert grade.source_support_score == 0
    assert grade.passed is False
    assert "alias_set_mismatch" in grade.mismatches
    assert "unsupported_alias:MADE-UP" in grade.hard_failures


def test_distinct_concepts_merged_as_aliases_is_a_hard_failure():
    task = _load_tasks()[1]
    prediction = TermUnitProposal(
        relationship="aliases",
        units=[
            ProposedTermUnit(
                term="명목금리",
                aliases=["실질금리"],
            )
        ],
        reason="평가용 병합 오류",
    )

    grade = grade_segmentation(task, prediction)

    assert grade.passed is False
    assert "merged_distinct_concepts" in grade.hard_failures


def test_notation_split_is_a_hard_failure():
    task = _load_tasks()[3]
    prediction = TermUnitProposal(
        relationship="distinct_concepts",
        units=[
            ProposedTermUnit(term="산업연관표", aliases=[]),
            ProposedTermUnit(term="I/O Tables", aliases=[]),
        ],
        reason="평가용 과분리 오류",
    )

    grade = grade_segmentation(task, prediction)

    assert grade.passed is False
    assert "over_split_notation" in grade.hard_failures


@pytest.mark.asyncio
async def test_repeated_runner_calculates_pass_at_1_and_pass_power_3():
    task = _load_tasks()[0]

    async def exact_proposer(_source_term, _raw_definition):
        return TermUnitProposal(
            relationship=task.expected.relationship,
            units=[
                ProposedTermUnit(term=unit.term, aliases=unit.aliases)
                for unit in task.expected.units
            ],
            reason="평가 하니스 테스트",
        )

    run = await run_segmentation_trials(
        [task],
        repeats=3,
        proposer=exact_proposer,
    )

    assert len(run.trials) == 3
    assert run.metrics.pass_at_1 == 1
    assert run.metrics.pass_power_k == 1
    assert run.metrics.passed_trial_count == 3
