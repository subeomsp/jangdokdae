import json

import pytest
from pydantic import ValidationError

from scripts.judge_learning_candidates_v4 import _cached_payload
from services.learning_editorial import (
    JUDGE_PROMPT_VERSION,
    CandidateJudgmentV4,
    DayJudgmentV4,
    normalize_judgments,
)


def _payload(**overrides):
    payload = {
        "issue_id": 1,
        "learn_value": 8,
        "focus_fit": 7,
        "context_fit": 4,
        "discovery_fit": 6,
        "explains_why": True,
        "topic_overlap": False,
        "has_new_development": True,
        "matched_previous_issue_ids": [],
        "reason": "판정 근거",
    }
    payload.update(overrides)
    return payload


def test_v4_judgment_requires_matched_issue_for_topic_overlap():
    with pytest.raises(ValidationError):
        CandidateJudgmentV4.model_validate(
            _payload(topic_overlap=True, matched_previous_issue_ids=[])
        )


def test_v4_judgment_normalizes_non_overlap_semantics_by_validation():
    with pytest.raises(ValidationError):
        CandidateJudgmentV4.model_validate(
            _payload(topic_overlap=False, has_new_development=False)
        )


def test_v4_judgment_accepts_repeat_with_a_new_development():
    judgment = CandidateJudgmentV4.model_validate(
        _payload(
            topic_overlap=True,
            has_new_development=True,
            matched_previous_issue_ids=[9],
        )
    )

    assert judgment.matched_previous_issue_ids == [9]


def test_v4_cache_is_bound_to_candidates_and_comparison_history(tmp_path):
    path = tmp_path / "judgments-v4.json"
    judgment = _payload()
    path.write_text(
        json.dumps(
            {
                "prompt_version": JUDGE_PROMPT_VERSION,
                "compared_issue_ids": [9],
                "candidate_issue_ids": [1],
                "judgments": [judgment],
            }
        )
    )

    assert _cached_payload(path, [9], [1]) is not None
    assert _cached_payload(path, [8], [1]) is None
    assert _cached_payload(path, [9], [2]) is None


def test_v4_rejects_match_to_a_current_candidate():
    result = DayJudgmentV4.model_validate(
        {
            "judgments": [
                _payload(
                    topic_overlap=True,
                    matched_previous_issue_ids=[20],
                )
            ]
        }
    )

    with pytest.raises(RuntimeError, match="최근 발행분에 없습니다"):
        normalize_judgments(
            "2026-07-17",
            result,
            candidate_ids=[1],
            previous_ids={9},
        )
