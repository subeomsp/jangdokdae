from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IssueCardResponse(BaseModel):
    id: int
    title: str
    teaser: str
    category: str
    source: str
    article_count: int
    created_at: datetime


class IssueListResponse(BaseModel):
    items: list[IssueCardResponse]
    total: int
    limit: int
    offset: int


class IssueReaderCardResponse(BaseModel):
    head: str
    paragraphs: list[str]


class IssueTermResponse(BaseModel):
    name: str
    definition: str
    aliases: list[str] = Field(default_factory=list)
    source_label: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_page: int | None = None
    original_url: str | None = None
    ai_generated: bool = True
    verification_status: str = "legacy"


class SourceArticleResponse(BaseModel):
    id: str
    title: str
    url: str
    news_source: str
    published_at: datetime | None


class IssueDetailResponse(IssueCardResponse):
    cards: list[IssueReaderCardResponse]
    terms: list[IssueTermResponse]
    sources: list[SourceArticleResponse]


class QuizQuestionResponse(BaseModel):
    quiz_id: str
    kind: str
    question: str
    options: list[str]


class QuizResponse(BaseModel):
    issue_id: int
    quizzes: list[QuizQuestionResponse]


class QuizSubmitRequest(BaseModel):
    answers: dict[str, int]


class QuizAnswerResultResponse(BaseModel):
    quiz_id: str
    kind: str
    selected_index: int | None
    answer_index: int
    is_correct: bool
    explanation: str


class QuizSubmitResponse(BaseModel):
    issue_id: int
    correct_count: int
    total_count: int
    results: list[QuizAnswerResultResponse]


class BookmarkUpdateRequest(BaseModel):
    bookmarked: bool


class IssueActivityMutationResponse(BaseModel):
    issue_id: int
    ok: bool = True


class DictionaryTermResponse(BaseModel):
    id: int
    term: str
    aliases: list[str] = Field(default_factory=list)
    term_type: str
    definition: str
    example: str | None
    source: str
    status: str
    source_url: str | None = None
    source_page: int | None = None
    is_ai_generated: bool = True
    verification_status: str = "legacy"
    quality_score: int | None = None


class DictionaryCandidateResponse(BaseModel):
    created: list[DictionaryTermResponse]
    skipped: list[str]


class DictionaryStatusUpdateRequest(BaseModel):
    status: Literal["approved", "rejected"]
