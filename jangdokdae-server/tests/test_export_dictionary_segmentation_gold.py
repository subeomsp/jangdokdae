import hashlib
from datetime import datetime
from types import SimpleNamespace

from scripts.export_dictionary_segmentation_gold import _task_from_source


def test_approved_source_becomes_gold_task():
    source_term = "간접금융/직접금융"
    raw_definition = "간접금융과 직접금융을 각각 설명하는 한국은행 공식 원문입니다."
    source = SimpleNamespace(
        term=source_term,
        term_units_status="approved",
        term_units_reviewed_at=datetime(2026, 7, 20, 20, 0, 0),
        term_units=[
            {
                "unit_index": 0,
                "term": "간접금융",
                "aliases": ["Indirect Financing"],
                "relationship": "distinct_concepts",
            },
            {
                "unit_index": 1,
                "term": "직접금융",
                "aliases": ["Direct Financing"],
                "relationship": "distinct_concepts",
            },
        ],
        source_version="2024",
        source_page=5,
        pdf_page=23,
        raw_definition=raw_definition,
        content_hash=hashlib.sha256(
            f"{source_term}\n{raw_definition}".encode()
        ).hexdigest(),
    )

    task = _task_from_source(
        source,
        task_id="bok-seg-006",
        batch_tag="batch_01",
    )

    assert task.label_status == "approved"
    assert task.expected.relationship == "distinct_concepts"
    assert [unit.term for unit in task.expected.units] == ["간접금융", "직접금융"]
    assert task.reviewed_at is not None
    assert task.reviewed_at.utcoffset() is not None
