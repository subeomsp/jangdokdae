"""한국은행 개별 용어 쉬운 설명 평가 Task 스키마."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReferenceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term_type: Literal["finance", "domain"]
    definition: str = Field(min_length=20, max_length=320)
    example: str | None = None


class DefinitionEvalTask(BaseModel):
    """사람이 승인한 설명과 공식 원문을 함께 고정한 평가 Task."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^bok-def-\d{3}$")
    label_status: Literal["approved"]
    source_code: Literal["bok_800"]
    source_version: str
    source_page: int = Field(ge=1)
    pdf_page: int = Field(ge=1)
    source_term: str = Field(min_length=1, max_length=200)
    source_unit_index: int = Field(ge=0)
    term: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    raw_definition: str = Field(min_length=10)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference: ReferenceDefinition
    required_concept_groups: list[list[str]] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    reviewed_by: str
    reviewed_at: datetime

    @model_validator(mode="after")
    def validate_source_hash(self) -> DefinitionEvalTask:
        expected_hash = hashlib.sha256(
            f"{self.source_term}\n{self.raw_definition}".encode()
        ).hexdigest()
        if self.content_hash != expected_hash:
            raise ValueError("content_hash does not match source_term and raw_definition")
        return self


def load_definition_tasks(path: Path) -> list[DefinitionEvalTask]:
    tasks: list[DefinitionEvalTask] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            tasks.append(DefinitionEvalTask.model_validate_json(line))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid task: {exc}") from exc
    if not tasks:
        raise ValueError(f"{path}: no evaluation tasks")
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate task ids")
    terms = [task.term for task in tasks]
    if len(terms) != len(set(terms)):
        raise ValueError(f"{path}: duplicate terms")
    return tasks
