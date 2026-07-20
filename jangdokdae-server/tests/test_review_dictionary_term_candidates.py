from types import SimpleNamespace

from scripts.review_dictionary_term_candidates import _approval_problems


def _source():
    return SimpleNamespace(
        term_units_status="approved",
        term_units=[
            {
                "unit_index": 0,
                "term": "간접금융",
                "aliases": ["Indirect Financing"],
            }
        ],
        raw_definition=(
            "간접금융은 금융기관이 일반 대중으로부터 예금을 받아 "
            "기업에 빌려주는 방식이다."
        ),
    )


def _candidate(**overrides):
    values = {
        "status": "candidate",
        "source": "bok_800",
        "verification_status": "verified",
        "quality_score": 95,
        "generation_prompt_version": "bok-definition-v2-human-feedback",
        "source_unit_index": 0,
        "term": "간접금융",
        "aliases": ["Indirect Financing"],
        "term_type": "finance",
        "definition": "간접금융은 금융기관이 예금을 받아 기업에 빌려주는 자금 중개 방식입니다.",
        "example": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_valid_reviewed_candidate_has_no_approval_problems():
    assert _approval_problems(_candidate(), _source()) == []


def test_low_score_and_alias_mismatch_block_approval():
    row = _candidate(quality_score=88, aliases=[])

    assert _approval_problems(row, _source()) == [
        "quality_score:88",
        "source_unit_alias_mismatch",
    ]
