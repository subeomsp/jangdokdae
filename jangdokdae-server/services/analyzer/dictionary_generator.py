"""Dictionary 후보 생성기.

공식 원문이 있는 용어는 원문만을 근거로 쉬운 설명을 만들고, 별도 모델이 근거 일치
여부를 검증한다. 기존 term-only 생성 함수는 레거시 후보 API와의 호환을 위해 남긴다.
"""

import re
from time import perf_counter
from typing import Literal, TypedDict, cast

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator

from app.config import settings

GROUNDED_DICTIONARY_PROMPT_VERSION = "bok-definition-v5"
GROUNDED_DICTIONARY_MIN_SCORE = 90
GROUNDED_DICTIONARY_MAX_ATTEMPTS = 2
_FORMAL_SENTENCE_END_RE = re.compile(r"[가-힣]니다(?=[.!?]|$)")
_FORMAL_FINAL_END_RE = re.compile(r"[가-힣]니다[.!?]?$")


class DictionaryDraft(BaseModel):
    term_type: Literal["finance", "domain"] = Field(description="용어 유형")
    definition: str = Field(description="주린이가 이해하기 쉬운 한두 문장 설명")
    example: str | None = Field(default=None, description="짧은 예시 문장")

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


class GroundedDictionaryAttempt(BaseModel):
    attempt_number: int = Field(ge=1)
    latency_ms: int = Field(ge=0)
    draft: DictionaryDraft
    deterministic_problems: list[str]
    verdict: GroundingVerdict


class GroundedDictionaryResult(BaseModel):
    attempts: list[GroundedDictionaryAttempt] = Field(min_length=1)

    @property
    def final_attempt(self) -> GroundedDictionaryAttempt:
        return self.attempts[-1]

    @property
    def passed(self) -> bool:
        attempt = self.final_attempt
        return (
            not attempt.deterministic_problems
            and attempt.verdict.supported
            and attempt.verdict.score >= GROUNDED_DICTIONARY_MIN_SCORE
        )


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
    quality_feedback: str | None = None,
) -> DictionaryDraft:
    """한국은행 원문 범위 안에서만 화면용 설명을 생성한다."""

    review_feedback_block = (
        "\n\n[사람 검수 피드백]\n"
        f"{review_feedback}\n"
        "피드백에서 지적한 문제를 고치되 공식 원문 밖의 정보는 추가하지 않는다."
        if review_feedback
        else ""
    )
    quality_feedback_block = (
        "\n\n[자동 검증 피드백]\n"
        f"{quality_feedback}\n"
        "이전 후보의 실패 원인을 고치되 공식 원문 밖의 정보는 추가하지 않는다."
        if quality_feedback
        else ""
    )
    prompt = (
        "너는 초보 투자자를 위한 경제 용어 편집자다.\n"
        "아래 [공식 원문]만 근거로 사용한다. 원문에 없는 사실, 수치, 최신 상황, "
        "전망을 추가하거나 상식으로 보완하지 않는다.\n"
        "공식 원문에 여러 개념이 함께 있어도 [용어] 하나에 해당하는 내용만 설명한다. "
        "다른 개념의 정의를 섞거나 두 개념을 하나처럼 설명하지 않는다.\n"
        "원문이 [용어] 자체를 이루는 핵심 요소(함께 정의되는 개념, 핵심 수단·구성 "
        "요소·계산식)를 여러 개 제시하면 그중 중요한 항목을 생략하지 않는다. 일부 예시에만 "
        "해당하는 특징을 용어 전체의 정의로 일반화하지 않는다.\n"
        "다만 [용어]에서 비롯되는 하류 결과·영향·파급효과(다른 지표나 물가·수출 등으로 "
        "이어지는 연쇄 효과)가 원문에 길게 이어지면, 그것까지 모두 담지 말고 [용어]가 "
        "무엇이고 어떻게 산출·구성되는지에 집중해 요약한다.\n"
        "원문의 주체·대상·방향 관계를 바꾸지 말고 자연스러운 한국어 조사를 사용한다.\n"
        "돈이나 예금을 제공한 출처에는 '~에게 받다'가 아니라 '~로부터 받다'를 사용한다.\n"
        "핵심 의미를 1~3개의 짧은 문장으로 풀어 쓰고, 어려운 용어는 쉬운 말로 바꾼다.\n"
        "정의와 예시의 모든 문장은 '~입니다/~합니다' 문체로 통일한다.\n"
        "제출 전에 맞춤법과 오탈자를 확인하고 자연스러운 한국어 문장만 반환한다.\n"
        "매수·매도 권유나 투자 판단을 하지 않는다.\n"
        "예시는 원문의 의미만으로 만들 수 있을 때만 작성하고, 아니면 null로 둔다.\n\n"
        f"[용어]\n{term}\n\n"
        f"[공식 원문]\n{raw_definition}"
        f"{review_feedback_block}"
        f"{quality_feedback_block}"
    )
    draft = await _llm(grounded_dictionary_model_name()).ainvoke(prompt)
    return cast(DictionaryDraft, draft)


def validate_grounded_draft(raw_definition: str, draft: DictionaryDraft) -> list[str]:
    """모델 검증 전에 잡을 수 있는 명확한 품질 문제를 결정적으로 검사한다."""

    problems: list[str] = []
    definition = draft.definition.strip()
    if not 20 <= len(definition) <= 320:
        problems.append("definition_length")

    sentence_count = len(_FORMAL_SENTENCE_END_RE.findall(definition))
    if sentence_count == 0 or _FORMAL_FINAL_END_RE.search(definition) is None:
        problems.append("definition_style")
    if sentence_count > 3:
        problems.append("too_many_sentences")

    example = (draft.example or "").strip()
    if example:
        if len(example) > 240:
            problems.append("example_length")
        if _FORMAL_FINAL_END_RE.search(example) is None:
            problems.append("example_style")
        artifact_markers = ("#", "parameter", "instructions", "model should", "as per")
        if any(marker in example.casefold() for marker in artifact_markers):
            problems.append("example_artifact")

    banned = ("매수하세요", "매도하세요", "투자해야", "추천합니다", "수익을 보장")
    if any(phrase in f"{definition} {draft.example or ''}" for phrase in banned):
        problems.append("investment_advice")

    if re.search(r"[가-힣]+에게\s+예금을\s+받", f"{definition} {example}"):
        problems.append("unnatural_deposit_source_particle")

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
        "원문이 [용어] 자체를 이루는 핵심 요소(함께 정의되는 개념, 핵심 수단·구성 요소·"
        "계산식)를 여러 개 제시했는데 후보가 그중 일부만 남기거나, 일부 예시의 특징을 전체 "
        "정의로 일반화하면 supported=false다.\n"
        "다만 [용어]에서 비롯되는 하류 결과·영향·파급효과(다른 지표나 물가·수출 등으로 "
        "이어지는 연쇄 효과)를 짧은 설명이 생략하는 것은 근거 위반이 아니다. 누락 자체는 "
        "감점 사유가 아니며, 원문을 왜곡하거나 원문 밖 내용을 더했을 때만 supported=false다.\n"
        "후보 예시에 코드, 지시문, 메타 설명, 출력 형식의 흔적이 있으면 supported=false다.\n"
        "원문에 없는 원인·결과·수치·시점·전망이 하나라도 있으면 supported=false다.\n"
        "맞춤법 오류, 오탈자, 어색한 문장이 있으면 90점 미만을 준다.\n"
        "정확하면서 초보자가 이해하기 쉽고 투자 조언이 없을 때만 90점 이상을 준다.\n\n"
        f"[용어]\n{term}\n\n"
        f"[공식 원문]\n{raw_definition}\n\n"
        f"[후보 정의]\n{draft.definition}\n\n"
        f"[후보 예시]\n{draft.example or '(없음)'}"
    )
    verdict = await _verifier_llm(grounded_dictionary_model_name()).ainvoke(prompt)
    return cast(GroundingVerdict, verdict)


def _automatic_retry_feedback(
    deterministic_problems: list[str],
    verdict: GroundingVerdict,
) -> str:
    details: list[str] = []
    if deterministic_problems:
        details.append("자동 검사 문제: " + ", ".join(deterministic_problems))
    details.append("검증 의견: " + verdict.reason)
    return "\n".join(details)


async def generate_verified_grounded_dictionary_draft(
    term: str,
    raw_definition: str,
    *,
    review_feedback: str | None = None,
    max_attempts: int = GROUNDED_DICTIONARY_MAX_ATTEMPTS,
) -> GroundedDictionaryResult:
    """검증 실패 사유로 한 번 보정한 뒤 최종 후보와 전체 시도를 반환한다."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    attempts: list[GroundedDictionaryAttempt] = []
    quality_feedback: str | None = None
    for attempt_number in range(1, max_attempts + 1):
        timer = perf_counter()
        draft = await generate_grounded_dictionary_draft(
            term,
            raw_definition,
            review_feedback=review_feedback,
            quality_feedback=quality_feedback,
        )
        deterministic_problems = validate_grounded_draft(raw_definition, draft)
        verdict = await verify_grounded_dictionary_draft(
            term,
            raw_definition,
            draft,
        )
        attempt = GroundedDictionaryAttempt(
            attempt_number=attempt_number,
            latency_ms=round((perf_counter() - timer) * 1000),
            draft=draft,
            deterministic_problems=deterministic_problems,
            verdict=verdict,
        )
        attempts.append(attempt)
        if (
            not deterministic_problems
            and verdict.supported
            and verdict.score >= GROUNDED_DICTIONARY_MIN_SCORE
        ):
            break
        quality_feedback = _automatic_retry_feedback(
            deterministic_problems,
            verdict,
        )

    return GroundedDictionaryResult(attempts=attempts)
