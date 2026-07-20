from types import SimpleNamespace

import pytest

from scripts.generate_dictionary_term_candidates import _flatten_targets


def test_flatten_targets_uses_only_approved_units():
    approved = SimpleNamespace(
        id=10,
        source_url="https://example.com/source",
        source_page=5,
        raw_definition="간접금융과 직접금융의 공식 원문",
        term_units_status="approved",
        term_units=[
            {
                "unit_index": 0,
                "term": "간접금융",
                "aliases": ["Indirect Financing"],
            },
            {
                "unit_index": 1,
                "term": "직접금융",
                "aliases": ["Direct Financing"],
            },
        ],
    )
    pending = SimpleNamespace(
        id=11,
        source_url="https://example.com/pending",
        source_page=6,
        raw_definition="미승인 원문",
        term_units_status="pending",
        term_units=[{"unit_index": 0, "term": "미승인", "aliases": []}],
    )

    targets = _flatten_targets([approved, pending], ["직접금융"])

    assert len(targets) == 1
    assert targets[0].term == "직접금융"
    assert targets[0].unit_index == 1
    assert targets[0].aliases == ["Direct Financing"]


def test_flatten_targets_rejects_unknown_unit():
    with pytest.raises(ValueError, match="approved term units not found"):
        _flatten_targets([], ["없는 용어"])
