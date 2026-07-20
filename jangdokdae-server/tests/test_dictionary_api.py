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
    GroundingVerdict,
    generate_dictionary_draft,
    generate_grounded_dictionary_draft,
    generate_verified_grounded_dictionary_draft,
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
    assert "일부 예시에만 해당하는 특징을 용어 전체의 정의로 일반화하지 않는다" in captured[
        "prompt"
    ]


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


@pytest.mark.asyncio
async def test_grounded_dictionary_prompt_includes_automatic_quality_feedback(
    monkeypatch,
):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return DictionaryDraft(
                term_type="finance",
                definition="수정된 원문 기반 설명입니다.",
            )

    monkeypatch.setattr(
        "services.analyzer.dictionary_generator._llm", lambda _model: FakeLlm()
    )

    await generate_grounded_dictionary_draft(
        "경기조절정책",
        "정부의 재정정책과 중앙은행의 통화정책을 활용한다.",
        quality_feedback="통화정책을 빠뜨리지 않는다.",
    )

    assert "[자동 검증 피드백]" in captured["prompt"]
    assert "통화정책을 빠뜨리지 않는다" in captured["prompt"]


@pytest.mark.asyncio
async def test_grounded_dictionary_pipeline_retries_failed_draft(monkeypatch):
    quality_feedbacks = []
    drafts = [
        DictionaryDraft(
            term_type="finance",
            definition="금융기관이 일반 대중에게 예금을 받아 자금을 중개합니다.",
        ),
        DictionaryDraft(
            term_type="finance",
            definition="금융기관이 일반 대중으로부터 예금을 받아 자금을 중개합니다.",
        ),
    ]

    async def fake_generate(
        _term,
        _raw_definition,
        review_feedback=None,
        quality_feedback=None,
    ):
        quality_feedbacks.append(quality_feedback)
        return drafts.pop(0)

    async def fake_verify(_term, _raw_definition, draft):
        supported = "대중으로부터" in draft.definition
        return GroundingVerdict(
            supported=supported,
            score=95 if supported else 0,
            reason="조사를 수정했습니다." if supported else "예금 출처의 조사가 어색합니다.",
        )

    monkeypatch.setattr(
        "services.analyzer.dictionary_generator.generate_grounded_dictionary_draft",
        fake_generate,
    )
    monkeypatch.setattr(
        "services.analyzer.dictionary_generator.verify_grounded_dictionary_draft",
        fake_verify,
    )

    result = await generate_verified_grounded_dictionary_draft(
        "간접금융",
        "금융기관이 일반 대중으로부터 예금을 받아 자금을 중개한다.",
    )

    assert len(result.attempts) == 2
    assert result.passed is True
    assert quality_feedbacks[0] is None
    assert "unnatural_deposit_source_particle" in quality_feedbacks[1]
    assert "예금 출처의 조사가 어색합니다" in quality_feedbacks[1]


def test_grounded_dictionary_validator_rejects_new_numbers_and_advice():
    draft = DictionaryDraft(
        term_type="finance",
        definition="이 지표가 10%를 넘으면 주식을 매수하세요.",
        example=None,
    )

    assert validate_grounded_draft("위험을 나타내는 지표이다.", draft) == [
        "definition_style",
        "investment_advice",
        "unsupported_number",
    ]


def test_grounded_dictionary_validator_rejects_meta_example_artifact():
    draft = DictionaryDraft(
        term_type="finance",
        definition="경제활동인구는 일할 능력과 의사가 있는 사람입니다.",
        example=")) # example is None as per instructions.",
    )

    assert validate_grounded_draft(
        "경제활동인구는 일할 능력과 의사가 있는 사람이다.",
        draft,
    ) == ["example_style", "example_artifact"]


def test_dictionary_draft_allows_omitted_example_field():
    draft = DictionaryDraft.model_validate(
        {
            "term_type": "finance",
            "definition": "경제활동인구는 일할 능력과 일할 의사가 있는 사람입니다.",
        }
    )

    assert draft.example is None


def test_grounded_dictionary_validator_rejects_unnatural_deposit_particle():
    draft = DictionaryDraft(
        term_type="finance",
        definition="금융기관은 일반 대중에게 예금을 받아 기업에 대출합니다.",
    )

    assert validate_grounded_draft(
        "금융기관은 일반 대중으로부터 예금을 받아 기업에 대출한다.",
        draft,
    ) == ["unnatural_deposit_source_particle"]


@pytest.mark.parametrize(
    ("definition", "example"),
    [
        (
            "경기조절정책은 경기의 움직임을 안정시키는 정책을 말합니다.",
            "정부와 중앙은행이 각자의 정책 수단으로 경기를 조절합니다.",
        ),
        (
            "직접금융은 주식이나 채권을 발행해 자금을 마련하는 방식에 해당합니다.",
            "기업이 필요한 자금을 주식 발행으로 직접 마련합니다.",
        ),
        (
            "노동생산성은 노동 투입량과 생산량을 비교해 살펴봅니다.",
            "생산량을 노동시간으로 나누어 변화를 확인합니다.",
        ),
        (
            "경제활동인구는 취업자와 실업자로 나뉩니다.",
            "조사 대상자를 두 집단으로 나누어 집계합니다.",
        ),
    ],
)
def test_grounded_dictionary_validator_accepts_formal_bieup_nida_endings(
    definition,
    example,
):
    draft = DictionaryDraft(
        term_type="finance",
        definition=definition,
        example=example,
    )

    assert validate_grounded_draft("공식 원문에는 숫자가 없다.", draft) == []


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
