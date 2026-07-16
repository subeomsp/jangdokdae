"""LLM 클라이언트 팩토리 — 분류(호출 A)·생성(호출 B)용 구조화 출력 체인.

두 호출 모두 gemini에 with_structured_output(Pydantic)을 씌워 JSON 파싱 오류를 제거한다(설계 10 §3).
백엔드는 settings.google_api_key가 있으면 google-genai(Gemini API 키), 없으면 Vertex AI(ADC/IAM)다.
임베딩 클라이언트(services/embedder/embedding_client.py)의 모델·리전 분기와 같은 설정 출처를 쓴다.
"""

from __future__ import annotations

from app.config import settings
from services.analyzer.schemas import ClassificationResult, ContentDraft


def _chat(temperature: float):  # noqa: ANN201 — 백엔드별 구체 타입 노출은 과함
    """공통 chat 모델. API 키가 있으면 genai(Gemini API), 없으면 Vertex(ADC)로 호출한다."""
    if settings.google_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.vertex_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            max_retries=settings.llm_max_retries,
        )
    from langchain_google_vertexai import ChatVertexAI

    return ChatVertexAI(
        model=settings.vertex_model,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=temperature,
        max_retries=settings.llm_max_retries,
    )


def make_classifier():  # noqa: ANN201 — Runnable 제네릭 타입 노출은 과함
    """호출 A — 결정적 분류기. invoke(messages) → ClassificationResult."""
    return _chat(settings.classify_temperature).with_structured_output(ClassificationResult)


def make_generator():  # noqa: ANN201
    """호출 B — 본문 생성기. invoke(messages) → ContentDraft."""
    return _chat(settings.generate_temperature).with_structured_output(ContentDraft)
