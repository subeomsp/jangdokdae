"""Dictionary 후보 생성기.

공식 원문이 있는 용어는 원문만을 근거로 쉬운 설명을 만들고, 별도 모델이 근거 일치
여부를 검증한다. 기존 term-only 생성 함수는 레거시 후보 API와의 호환을 위해 남긴다.
"""

import re
from typing import Literal, TypedDict, cast

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator

from app.config import settings

GROUNDED_DICTIONARY_PROMPT_VERSION = "bok-definition-v2"
GROUNDED_DICTIONARY_MIN_SCORE = 90


class DictionaryDraft(BaseModel):
    term_type: Literal["finance", "domain"] = Field(description="용어 유형")
    definition: str = Field(description="주린이가 이해하기 쉬운 한두 문장 설명")
    example: str | None = Field(description="짧은 예시 문장")

    @field_validator("example", mode="before")
    @classmethod
    def normalize_empty_example(cls, value):
        if isinstance(value, str) and value.strip().casefold() in {
            "",
            "null",
            "none",
            "없음",
            "(없음)",
        }:
            return None
        return value


class GroundingVerdict(BaseModel):
    supported: bool = Field(description="설명이 원문만으로 뒷받침되는지 여부")
    score: int = Field(ge=0, le=100, description="원문 충실도와 초보자 가독성 점수")
    reason: str = Field(description="판정 근거")


class _State(TypedDict):
    term: str
    draft: DictionaryDraft | None


def _llm(model_name: str):
    return ChatVertexAI(
        model=model_name,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=0.2,
        max_retries=min(settings.llm_max_retries, 2),
        timeout=settings.dictionary_request_timeout_seconds,
    ).with_structured_output(DictionaryDraft)


def _verifier_llm(model_name: str):
    return ChatVertexAI(
        model=model_name,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=0,
        max_retries=min(settings.llm_max_retries, 2),
        timeout=settings.dictionary_request_timeout_seconds,
    ).with_structured_output(GroundingVerdict)


def grounded_dictionary_model_name() -> str:
    """공식 원문 요약은 현재 파이프라인에서 검증된 모델을 기본값으로 쓴다."""

    return settings.dictionary_grounded_model or settings.vertex_model


async def generate_dictionary_draft(term: str) -> DictionaryDraft:
    """LangGraph 단일 노드 생성. 실패 fallback은 호출부가 처리한다."""

    async def generate(state: _State) -> _State:
        prompt = (
            "너는 초보 투자자를 위한 주식/경제 용어 사전 작성자다.\n"
            "어려운 금융 용어를 또 늘어놓지 말고 쉽게 설명한다.\n"
            "투자 조언이나 매수/매도 판단은 하지 않는다.\n"
            "정의와 예시의 모든 문장은 '~입니다/~합니다' 문체로 통일한다.\n"
            f"용어: {state['term']}"
        )
        draft = await _llm(settings.dictionary_model).ainvoke(prompt)
        return {"term": state["term"], "draft": draft}

    graph = StateGraph(_State)
    graph.add_node("generate", generate)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    result = await graph.compile().ainvoke({"term": term, "draft": None})
    draft = result["draft"]
    if draft is None:
        raise RuntimeError("dictionary draft was not generated")
    return cast(DictionaryDraft, draft)


async def generate_grounded_dictionary_draft(
    term: str,
    raw_definition: str,
    review_feedback: str | None = None,
) -> DictionaryDraft:
    """한국은행 원문 범위 안에서만 화면용 설명을 생성한다."""

    feedback_block = (
        "\n\n[사람 검수 피드백]\n"
        f"{review_feedback}\n"
        "피드백에서 지적한 문제를 고치되 공식 원문 밖의 정보는 추가하지 않는다."
        if review_feedback
        else ""
    )
    prompt = (
        "너는 초보 투자자를 위한 경제 용어 편집자다.\n"
        "아래 [공식 원문]만 근거로 사용한다. 원문에 없는 사실, 수치, 최신 상황, "
        "전망을 추가하거나 상식으로 보완하지 않는다.\n"
        "공식 원문에 여러 개념이 함께 있어도 [용어] 하나에 해당하는 내용만 설명한다. "
        "다른 개념의 정의를 섞거나 두 개념을 하나처럼 설명하지 않는다.\n"
        "핵심 의미를 1~3개의 짧은 문장으로 풀어 쓰고, 어려운 용어는 쉬운 말로 바꾼다.\n"
        "정의와 예시의 모든 문장은 '~입니다/~합니다' 문체로 통일한다.\n"
        "제출 전에 맞춤법과 오탈자를 확인하고 자연스러운 한국어 문장만 반환한다.\n"
        "매수·매도 권유나 투자 판단을 하지 않는다.\n"
        "예시는 원문의 의미만으로 만들 수 있을 때만 작성하고, 아니면 null로 둔다.\n\n"
        f"[용어]\n{term}\n\n"
        f"[공식 원문]\n{raw_definition}"
        f"{feedback_block}"
    )
    draft = await _llm(grounded_dictionary_model_name()).ainvoke(prompt)
    return cast(DictionaryDraft, draft)


def validate_grounded_draft(raw_definition: str, draft: DictionaryDraft) -> list[str]:
    """모델 검증 전에 잡을 수 있는 명확한 품질 문제를 결정적으로 검사한다."""

    problems: list[str] = []
    definition = draft.definition.strip()
    if not 20 <= len(definition) <= 320:
        problems.append("definition_length")

    sentence_count = len(re.findall(r"(?:습니다|입니다)[.!?]?", definition))
    if sentence_count > 3:
        problems.append("too_many_sentences")

    banned = ("매수하세요", "매도하세요", "투자해야", "추천합니다", "수익을 보장")
    if any(phrase in f"{definition} {draft.example or ''}" for phrase in banned):
        problems.append("investment_advice")

    raw_numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", raw_definition))
    draft_numbers = set(re.findall(r"\d+(?:[.,]\d+)?%?", f"{definition} {draft.example or ''}"))
    if draft_numbers - raw_numbers:
        problems.append("unsupported_number")
    return problems


async def verify_grounded_dictionary_draft(
    term: str,
    raw_definition: str,
    draft: DictionaryDraft,
) -> GroundingVerdict:
    """생성 모델과 분리된 판정 단계로 원문 충실도를 검사한다."""

    deterministic_problems = validate_grounded_draft(raw_definition, draft)
    if deterministic_problems:
        return GroundingVerdict(
            supported=False,
            score=0,
            reason=f"자동 품질 검사 실패: {', '.join(deterministic_problems)}",
        )

    prompt = (
        "너는 경제 용어 설명의 팩트체커다.\n"
        "후보 설명의 각 주장이 [공식 원문]에서 직접 뒷받침되는지 판정한다.\n"
        "후보가 [용어]가 아닌 다른 개념의 정의를 섞거나 여러 개념을 하나처럼 설명하면 "
        "supported=false다.\n"
        "원문에 없는 원인·결과·수치·시점·전망이 하나라도 있으면 supported=false다.\n"
        "맞춤법 오류, 오탈자, 어색한 문장이 있으면 80점 미만을 준다.\n"
        "정확하면서 초보자가 이해하기 쉽고 투자 조언이 없을 때만 80점 이상을 준다.\n\n"
        f"[용어]\n{term}\n\n"
        f"[공식 원문]\n{raw_definition}\n\n"
        f"[후보 정의]\n{draft.definition}\n\n"
        f"[후보 예시]\n{draft.example or '(없음)'}"
    )
    verdict = await _verifier_llm(grounded_dictionary_model_name()).ainvoke(prompt)
    return cast(GroundingVerdict, verdict)
