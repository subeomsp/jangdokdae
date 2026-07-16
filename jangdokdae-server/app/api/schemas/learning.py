"""하루 세 가지 이슈 학습 흐름의 요청·응답 스키마."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.api.models import IssueCardResponse, QuizQuestionResponse

LearningRole = Literal["focus", "context", "discovery"]


class DailyLearningItemResponse(BaseModel):
    position: int
    role: LearningRole
    role_label: str
    reason: str
    issue: IssueCardResponse
    quiz: QuizQuestionResponse
    completed: bool = False


class DailyLearningResponse(BaseModel):
    learning_date: date
    items: list[DailyLearningItemResponse]
    completed_count: int
    total_count: int
    is_complete: bool
    personalized: bool


class DailyQuizSubmitRequest(BaseModel):
    selected_index: int = Field(ge=0, le=3)


class DailyQuizSubmitResponse(BaseModel):
    issue_id: int
    quiz_id: str
    selected_index: int
    answer_index: int
    is_correct: bool
    explanation: str
