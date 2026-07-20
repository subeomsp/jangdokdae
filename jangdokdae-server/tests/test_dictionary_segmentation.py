import pytest

from services.analyzer.dictionary_segmentation import (
    ProposedTermUnit,
    TermUnitProposal,
    deterministic_single_proposal,
    has_top_level_slash,
    proposal_to_records,
    propose_term_units,
    validate_term_unit_proposal,
)


def test_top_level_slash_ignores_abbreviation_parentheses():
    assert has_top_level_slash("단리/복리") is True
    assert has_top_level_slash("산업연관표(I/O Tables)") is False
    assert has_top_level_slash("Treasury Bill(T/B)") is False


def test_notation_slash_is_kept_as_one_term_without_llm():
    proposal = deterministic_single_proposal("산업연관표(I/O Tables)")

    assert proposal is not None
    assert proposal.relationship == "notation"
    assert [unit.term for unit in proposal.units] == ["산업연관표(I/O Tables)"]
    assert proposal.units[0].aliases == ["산업연관표", "I/O Tables"]


def test_single_term_uses_explicit_english_alias_from_definition():
    proposal = deterministic_single_proposal(
        "빅테크",
        "빅테크(Big Tech)는 규모가 크고 영향력이 큰 기술 기업들을 통칭한다.",
    )

    assert proposal is not None
    assert proposal.relationship == "single"
    assert proposal.units[0].term == "빅테크"
    assert proposal.units[0].aliases == ["Big Tech"]


def test_distinct_proposal_requires_multiple_supported_units():
    valid = TermUnitProposal(
        relationship="distinct_concepts",
        units=[
            ProposedTermUnit(term="단리", aliases=[]),
            ProposedTermUnit(term="복리", aliases=[]),
        ],
        reason="이자를 계산하는 서로 다른 방식입니다.",
    )
    invalid = TermUnitProposal(
        relationship="distinct_concepts",
        units=[ProposedTermUnit(term="단리", aliases=[])],
        reason="하나만 있습니다.",
    )
    raw = "단리는 원금에 대해서만 이자를 계산하고 복리는 이자에도 이자를 계산한다."

    assert validate_term_unit_proposal("단리/복리", raw, valid) == []
    assert "distinct_requires_multiple_units" in validate_term_unit_proposal(
        "단리/복리", raw, invalid
    )


@pytest.mark.asyncio
async def test_compound_proposal_uses_official_source_only(monkeypatch):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return TermUnitProposal(
                relationship="aliases",
                units=[
                    ProposedTermUnit(
                        term="환매조건부매매",
                        aliases=["RP", "Repo", "RP"],
                    )
                ],
                reason="같은 거래를 가리키는 다른 표기입니다.",
            )

    monkeypatch.setattr(
        "services.analyzer.dictionary_segmentation._segmentation_llm",
        lambda _model: FakeLlm(),
    )
    proposal = await propose_term_units(
        "환매조건부매매/RP/Repo",
        "환매조건부매매는 RP 또는 Repo라고도 부른다.",
    )

    assert "제목과 [공식 원문]에 있는 정보만 사용" in captured["prompt"]
    assert proposal.units[0].aliases == ["RP", "Repo"]
    assert proposal_to_records(proposal) == [
        {
            "unit_index": 0,
            "term": "환매조건부매매",
            "aliases": ["RP", "Repo"],
            "relationship": "aliases",
        }
    ]


def test_proposal_rejects_unsupported_alias():
    proposal = TermUnitProposal(
        relationship="aliases",
        units=[ProposedTermUnit(term="환매조건부매매", aliases=["없는약어"])],
        reason="검증용",
    )

    assert validate_term_unit_proposal(
        "환매조건부매매/RP",
        "환매조건부매매는 RP라고도 한다.",
        proposal,
    ) == ["unsupported_alias:없는약어"]
