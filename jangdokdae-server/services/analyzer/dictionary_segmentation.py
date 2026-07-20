"""한국은행 복합 제목을 화면용 개별 용어 단위로 나누는 제안기."""

from __future__ import annotations

import re
from typing import Literal, cast

from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field

from app.config import settings
from services.analyzer.bok_dictionary import build_aliases, normalize_term
from services.analyzer.dictionary_generator import grounded_dictionary_model_name

TermRelationship = Literal["single", "distinct_concepts", "aliases", "notation"]
SEGMENTATION_PROMPT_VERSION = "bok-term-units-v2"


class ProposedTermUnit(BaseModel):
    term: str = Field(description="화면에 표시할 하나의 대표 용어")
    aliases: list[str] = Field(
        default_factory=list,
        description="같은 개념을 가리키는 약어와 다른 표기",
    )


class TermUnitProposal(BaseModel):
    relationship: TermRelationship
    units: list[ProposedTermUnit]
    reason: str = Field(description="분리 또는 비분리 판단 근거")


def _segmentation_llm(model_name: str):
    return ChatVertexAI(
        model=model_name,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=0,
        max_retries=min(settings.llm_max_retries, 2),
        timeout=settings.dictionary_request_timeout_seconds,
    ).with_structured_output(TermUnitProposal)


def has_top_level_slash(term: str) -> bool:
    """괄호 밖에 실제 구분자로 볼 수 있는 ``/``가 있는지 확인한다."""

    depth = 0
    for character in term:
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif character == "/" and depth == 0:
            return True
    return False


def _explicit_english_aliases(label: str, source_text: str) -> list[str]:
    """``용어(BCBS; English Name)``에서 영문 표기만 결정적으로 추출한다."""

    aliases: list[str] = []
    pattern = rf"{re.escape(normalize_term(label))}\s*\(([^(){{}}]{{2,120}})\)"
    for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
        for part in re.split(r"[;,]", match.group(1)):
            alias = normalize_term(part)
            if not re.search(r"[A-Za-z]{2}", alias):
                continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+&'/_-]{1,119}", alias):
                continue
            aliases.append(alias)
    return list(dict.fromkeys(aliases))


def enrich_explicit_aliases(
    source_term: str,
    raw_definition: str,
    proposal: TermUnitProposal,
) -> TermUnitProposal:
    """대표 용어와 이미 찾은 별칭 바로 뒤의 공식 영문 표기를 같은 unit에 보강한다."""

    source_text = f"{source_term}\n{raw_definition}"
    units: list[ProposedTermUnit] = []
    for unit in proposal.units:
        aliases = list(unit.aliases)
        for label in [unit.term, *unit.aliases]:
            aliases.extend(_explicit_english_aliases(label, source_text))
        aliases = [
            alias
            for alias in dict.fromkeys(aliases)
            if alias.casefold() != unit.term.casefold()
        ]
        units.append(ProposedTermUnit(term=unit.term, aliases=aliases))
    return TermUnitProposal(
        relationship=proposal.relationship,
        units=units,
        reason=proposal.reason,
    )


def deterministic_single_proposal(
    source_term: str,
    raw_definition: str = "",
) -> TermUnitProposal | None:
    """복합 제목이 아닌 항목과 괄호 속 약어의 slash를 AI 호출 없이 처리한다."""

    if has_top_level_slash(source_term):
        return None
    relationship: TermRelationship = "notation" if "/" in source_term else "single"
    alias_candidates = build_aliases(source_term)
    aliases = [
        alias
        for alias in dict.fromkeys(alias_candidates)
        if alias.casefold() != normalize_term(source_term).casefold()
    ]
    return enrich_explicit_aliases(
        source_term,
        raw_definition,
        TermUnitProposal(
            relationship=relationship,
            units=[ProposedTermUnit(term=normalize_term(source_term), aliases=aliases)],
            reason=(
                "slash가 괄호 안 약어 표기에만 있어 하나의 용어로 유지합니다."
                if relationship == "notation"
                else "제목에 복합 용어 구분자가 없어 하나의 용어로 유지합니다."
            ),
        ),
    )


def normalize_proposal(proposal: TermUnitProposal) -> TermUnitProposal:
    units: list[ProposedTermUnit] = []
    seen_terms: set[str] = set()
    for unit in proposal.units:
        term = normalize_term(unit.term)
        term_key = term.casefold()
        if not term or term_key in seen_terms:
            continue
        seen_terms.add(term_key)
        aliases: list[str] = []
        seen_aliases = {term_key}
        for value in unit.aliases:
            alias = normalize_term(value)
            alias_key = alias.casefold()
            if alias and alias_key not in seen_aliases:
                seen_aliases.add(alias_key)
                aliases.append(alias)
        units.append(ProposedTermUnit(term=term, aliases=aliases))
    return TermUnitProposal(
        relationship=proposal.relationship,
        units=units,
        reason=proposal.reason.strip(),
    )


def _label_has_source_support(label: str, source_text: str) -> bool:
    normalized_label = re.sub(r"[\s()/·+\-]", "", label).casefold()
    normalized_source = re.sub(r"[\s()/·+\-]", "", source_text).casefold()
    if normalized_label and normalized_label in normalized_source:
        return True

    tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}|\d+", label)
    return bool(tokens) and all(
        re.sub(r"\s+", "", token).casefold() in normalized_source for token in tokens
    )


def validate_term_unit_proposal(
    source_term: str,
    raw_definition: str,
    proposal: TermUnitProposal,
) -> list[str]:
    """저장 전에 구조와 원문 표기 근거를 결정적으로 검사한다."""

    problems: list[str] = []
    units = proposal.units
    if not 1 <= len(units) <= 8:
        problems.append("unit_count")
    if proposal.relationship == "distinct_concepts" and len(units) < 2:
        problems.append("distinct_requires_multiple_units")
    if proposal.relationship in {"single", "aliases", "notation"} and len(units) != 1:
        problems.append("single_relationship_requires_one_unit")

    source_text = f"{source_term} {raw_definition}"
    terms = [unit.term.casefold() for unit in units]
    if len(terms) != len(set(terms)):
        problems.append("duplicate_terms")

    for unit in units:
        if not 1 <= len(unit.term) <= 100:
            problems.append(f"invalid_term_length:{unit.term}")
        if not _label_has_source_support(unit.term, source_text):
            problems.append(f"unsupported_term:{unit.term}")
        for alias in unit.aliases:
            if not _label_has_source_support(alias, source_text):
                problems.append(f"unsupported_alias:{alias}")
    return problems


async def propose_term_units(
    source_term: str,
    raw_definition: str,
) -> TermUnitProposal:
    """원문을 수정하지 않고 화면용 용어 분리안만 반환한다."""

    deterministic = deterministic_single_proposal(source_term, raw_definition)
    if deterministic is not None:
        return deterministic

    prompt = (
        "너는 한국은행 경제금융용어 원문의 제목을 화면용 사전 단위로 정리하는 편집자다.\n"
        "제목과 [공식 원문]에 있는 정보만 사용하고 새로운 용어나 의미를 만들지 않는다.\n"
        "relationship은 아래 네 값 중 하나다.\n"
        "- distinct_concepts: 서로 따로 설명하고 검색해야 하는 개념들\n"
        "- aliases: 같은 개념의 정식명칭, 약어, 다른 표기\n"
        "- notation: slash가 통화쌍이나 약어 표기의 일부라 분리하면 안 됨\n"
        "- single: 그 밖의 단일 개념\n"
        "distinct_concepts일 때만 units를 두 개 이상 만든다.\n"
        "aliases, notation, single은 대표 용어 하나만 만들고 나머지 표기는 aliases에 넣는다.\n"
        "원문에서 용어 바로 뒤 괄호에 영문명이나 약어가 명시되면 해당 unit의 aliases에 "
        "빠짐없이 포함한다.\n"
        "생략형 제목은 원문이 직접 뒷받침할 때만 완전한 용어로 복원한다.\n"
        "예: 단리/복리 → distinct_concepts, 단리와 복리\n"
        "예: 환매조건부매매/RP/Repo → aliases, 대표 용어 환매조건부매매\n"
        "예: 산업연관표(I/O Tables) → notation, 분리하지 않음\n"
        "예: 원/위안 직거래시장 → notation, 분리하지 않음\n\n"
        f"[원문 제목]\n{source_term}\n\n"
        f"[공식 원문]\n{raw_definition}"
    )
    raw_proposal = await _segmentation_llm(grounded_dictionary_model_name()).ainvoke(prompt)
    proposal = normalize_proposal(cast(TermUnitProposal, raw_proposal))
    proposal = enrich_explicit_aliases(source_term, raw_definition, proposal)
    problems = validate_term_unit_proposal(source_term, raw_definition, proposal)
    if problems:
        raise ValueError(f"invalid term unit proposal: {', '.join(problems)}")
    return proposal


def proposal_to_records(proposal: TermUnitProposal) -> list[dict]:
    """DB ``term_units`` JSONB에 저장할 안정적인 형태로 바꾼다."""

    return [
        {
            "unit_index": index,
            "term": unit.term,
            "aliases": unit.aliases,
            "relationship": proposal.relationship,
        }
        for index, unit in enumerate(proposal.units)
    ]
