import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.api.models import DictionaryStatusUpdateRequest
from app.api.routers.dictionary import (
    create_candidates_from_issue,
    extract_terms,
    list_dictionary_terms,
    update_dictionary_term_status,
)
from services.analyzer.dictionary_generator import (
    DictionaryDraft,
    generate_dictionary_draft,
    generate_grounded_dictionary_draft,
    validate_grounded_draft,
)


def test_extract_terms_deduplicates_term_values_only():
    assert extract_terms(
        [
            {"term": "기준금리", "sentence": "첫 문장"},
            {"term": "기준금리", "sentence": "다른 문장"},
            {"term": "PER"},
            {"term": " "},
        ]
    ) == ["기준금리", "PER"]


@pytest.mark.asyncio
async def test_list_dictionary_terms_sets_total_count_header():
    response = Response()

    result = await list_dictionary_terms(
        response,
        status="approved",
        limit=6,
        offset=6,
        db=_FakeListDB(),
    )

    assert response.headers["X-Total-Count"] == "42"
    assert [item.term for item in result] == ["기준금리"]


@pytest.mark.asyncio
async def test_dictionary_prompt_requires_formal_korean_style(monkeypatch):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return DictionaryDraft(
                term_type="finance",
                definition="기준금리를 쉽게 설명합니다.",
                example="기준금리가 오르면 이자 부담이 커집니다.",
            )

    monkeypatch.setattr(
        "services.analyzer.dictionary_generator._llm", lambda _model: FakeLlm()
    )

    await generate_dictionary_draft("기준금리")

    assert "모든 문장은 '~입니다/~합니다' 문체로 통일한다" in captured["prompt"]


@pytest.mark.asyncio
async def test_grounded_dictionary_prompt_forbids_external_facts(monkeypatch):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return DictionaryDraft(
                term_type="finance",
                definition="기준금리는 중앙은행이 정하는 정책금리입니다.",
                example=None,
            )

    monkeypatch.setattr(
        "services.analyzer.dictionary_generator._llm", lambda _model: FakeLlm()
    )

    await generate_grounded_dictionary_draft(
        "기준금리", "중앙은행이 정책 수행을 위해 정하는 금리이다."
    )

    assert "아래 [공식 원문]만 근거로 사용한다" in captured["prompt"]
    assert "원문에 없는 사실, 수치, 최신 상황" in captured["prompt"]
    assert "[용어] 하나에 해당하는 내용만 설명한다" in captured["prompt"]


@pytest.mark.asyncio
async def test_grounded_dictionary_prompt_includes_human_review_feedback(monkeypatch):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return DictionaryDraft(
                term_type="finance",
                definition="수정된 원문 기반 설명입니다.",
                example=None,
            )

    monkeypatch.setattr(
        "services.analyzer.dictionary_generator._llm", lambda _model: FakeLlm()
    )

    await generate_grounded_dictionary_draft(
        "직접금융",
        "기업이 주식이나 채권을 발행해 자금을 조달한다.",
        review_feedback="주식 투자를 대출처럼 표현하지 않는다.",
    )

    assert "[사람 검수 피드백]" in captured["prompt"]
    assert "주식 투자를 대출처럼 표현하지 않는다" in captured["prompt"]


def test_grounded_dictionary_validator_rejects_new_numbers_and_advice():
    draft = DictionaryDraft(
        term_type="finance",
        definition="이 지표가 10%를 넘으면 주식을 매수하세요.",
        example=None,
    )

    assert validate_grounded_draft("위험을 나타내는 지표이다.", draft) == [
        "investment_advice",
        "unsupported_number",
    ]


@pytest.mark.parametrize("empty_value", ["null", "None", "없음", "(없음)", ""])
def test_dictionary_draft_normalizes_empty_example_strings(empty_value):
    draft = DictionaryDraft(
        term_type="finance",
        definition="한국은행 원문을 기반으로 작성한 쉬운 설명입니다.",
        example=empty_value,
    )

    assert draft.example is None


@pytest.mark.asyncio
async def test_create_candidates_skips_existing_terms(monkeypatch):
    async def fake_generate(term: str):
        return DictionaryDraft(
            term_type="finance",
            definition=f"{term} 쉬운 설명",
            example=f"{term} 예시",
        )

    monkeypatch.setattr("app.api.routers.dictionary.generate_dictionary_draft", fake_generate)
    db = _FakeDB(existing_terms=["PER"])

    result = await create_candidates_from_issue(82, db)

    assert [item.term for item in result.created] == ["기준금리"]
    assert result.created[0].definition == "기준금리 쉬운 설명"
    assert result.skipped == ["PER"]
    assert db.committed is True


@pytest.mark.asyncio
async def test_admin_can_approve_dictionary_candidate(monkeypatch):
    row = SimpleNamespace(
        id=1,
        term="기준금리",
        term_type="finance",
        definition="금리의 기준입니다.",
        example=None,
        source="llm",
        status="candidate",
    )
    db = _FakeReviewDB(row)
    monkeypatch.setattr("app.api.routers.dictionary.settings.dictionary_admin_token", "secret")

    result = await update_dictionary_term_status(
        "기준금리",
        DictionaryStatusUpdateRequest(status="approved"),
        "secret",
        db,
    )

    assert result.status == "approved"
    assert db.committed is True


@pytest.mark.asyncio
async def test_dictionary_review_rejects_invalid_admin_token(monkeypatch):
    monkeypatch.setattr("app.api.routers.dictionary.settings.dictionary_admin_token", "secret")

    with pytest.raises(HTTPException) as exc:
        await update_dictionary_term_status(
            "기준금리",
            DictionaryStatusUpdateRequest(status="approved"),
            "wrong",
            _FakeReviewDB(None),
        )

    assert exc.value.status_code == 403


class _FakeReviewDB:
    def __init__(self, row):
        self.row = row
        self.committed = False

    async def scalar(self, _stmt):
        return self.row

    async def commit(self):
        self.committed = True


class _FakeDB:
    def __init__(self, existing_terms: list[str]):
        self.existing_terms = existing_terms
        self.committed = False

    async def get(self, _model, issue_id: int):
        return SimpleNamespace(
            id=issue_id,
            term_spans=[
                {"term": "PER", "sentence": "기존"},
                {"term": "기준금리", "sentence": "신규"},
                {"term": "기준금리", "sentence": "중복"},
            ],
        )

    async def execute(self, _stmt):
        if self.existing_terms is not None:
            terms = self.existing_terms
            self.existing_terms = None
            return _ExistingResult(terms)
        return _InsertResult(
            SimpleNamespace(
                id=1,
                term="기준금리",
                term_type="finance",
                definition="기준금리 쉬운 설명",
                example="기준금리 예시",
                source="llm",
                status="candidate",
            )
        )

    async def commit(self):
        self.committed = True


class _ExistingResult:
    def __init__(self, terms: list[str]):
        self.terms = terms

    def scalars(self):
        return self

    def all(self):
        return self.terms


class _FakeListDB:
    async def scalar(self, _stmt):
        return 42

    async def execute(self, _stmt):
        return _ExistingResult([
            SimpleNamespace(
                id=1,
                term="기준금리",
                term_type="finance",
                definition="금리의 기준입니다.",
                example=None,
                source="llm",
                status="approved",
            )
        ])


class _InsertResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row
