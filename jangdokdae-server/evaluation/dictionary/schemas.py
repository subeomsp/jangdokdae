"""용어 분리 평가 Task 스키마와 안전한 로더."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.analyzer.dictionary_segmentation import TermRelationship

LabelStatus = Literal["draft", "approved"]


class ExpectedTermUnit(BaseModel):
    """사람이 정답으로 확정할 화면용 개별 용어."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)


class ExpectedSegmentation(BaseModel):
    """한 원문 제목에 대한 기대 분리 결과."""

    model_config = ConfigDict(extra="forbid")

    relationship: TermRelationship
    units: list[ExpectedTermUnit] = Field(min_length=1, max_length=8)


class SegmentationEvalTask(BaseModel):
    """원문과 사람 라벨을 함께 고정한 재현 가능한 평가 Task."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^bok-seg-\d{3}$")
    label_status: LabelStatus
    source_code: Literal["bok_800"]
    source_version: str
    source_page: int = Field(ge=1)
    pdf_page: int = Field(ge=1)
    source_term: str = Field(min_length=1, max_length=200)
    raw_definition: str = Field(min_length=10)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected: ExpectedSegmentation
    tags: list[str] = Field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_source_and_review(self) -> SegmentationEvalTask:
        expected_hash = hashlib.sha256(
            f"{self.source_term}\n{self.raw_definition}".encode()
        ).hexdigest()
        if self.content_hash != expected_hash:
            raise ValueError("content_hash does not match source_term and raw_definition")

        if self.label_status == "approved" and not (self.reviewed_by and self.reviewed_at):
            raise ValueError("approved labels require reviewed_by and reviewed_at")
        if self.label_status == "draft" and (self.reviewed_by or self.reviewed_at):
            raise ValueError("draft labels cannot contain review metadata")
        return self


def load_segmentation_tasks(
    path: Path,
    *,
    allow_draft: bool = False,
) -> list[SegmentationEvalTask]:
    """JSONL Task를 읽는다.

    기본값은 draft 라벨을 거부한다. 사람 검수 전 실험은 호출자가 ``allow_draft=True``를
    명시해야 하므로, 초안이 정식 골드셋이나 자동 승인 근거로 잘못 사용되지 않는다.
    """

    tasks: list[SegmentationEvalTask] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            task = SegmentationEvalTask.model_validate_json(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid task: {exc}") from exc
        tasks.append(task)

    if not tasks:
        raise ValueError(f"{path}: no evaluation tasks")

    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate task ids")

    drafts = [task.id for task in tasks if task.label_status == "draft"]
    if drafts and not allow_draft:
        raise ValueError(
            "draft labels are not an approved goldset; "
            f"review them first or explicitly allow draft: {', '.join(drafts)}"
        )
    return tasks
