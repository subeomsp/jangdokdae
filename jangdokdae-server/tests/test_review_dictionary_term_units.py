import pytest

from scripts.review_dictionary_term_units import _stored_proposal


def test_stored_proposal_restores_unit_order():
    proposal = _stored_proposal(
        [
            {
                "unit_index": 1,
                "term": "직접금융",
                "aliases": ["Direct Financing"],
                "relationship": "distinct_concepts",
            },
            {
                "unit_index": 0,
                "term": "간접금융",
                "aliases": ["Indirect Financing"],
                "relationship": "distinct_concepts",
            },
        ]
    )

    assert proposal.relationship == "distinct_concepts"
    assert [unit.term for unit in proposal.units] == ["간접금융", "직접금융"]


def test_stored_proposal_rejects_mixed_relationships():
    with pytest.raises(ValueError, match="inconsistent relationships"):
        _stored_proposal(
            [
                {
                    "unit_index": 0,
                    "term": "A",
                    "aliases": [],
                    "relationship": "single",
                },
                {
                    "unit_index": 1,
                    "term": "B",
                    "aliases": [],
                    "relationship": "distinct_concepts",
                },
            ]
        )
