"""DictionaryTerm ORM 모델 — 본문 용어 툴팁과 사전 화면의 공통 저장소."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import KST_NOW, Base


class DictionaryTerm(Base):
    __tablename__ = "dictionary_terms"
    __table_args__ = (
        UniqueConstraint("term", name="uq_dictionary_terms_term"),
        UniqueConstraint(
            "source_entry_id",
            "source_unit_index",
            name="uq_dictionary_terms_source_entry_unit",
        ),
        Index("ix_dictionary_terms_status", "status"),
        Index("ix_dictionary_terms_type", "term_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(100), nullable=False)
    # 원문 항목 전체의 별칭이 아니라 이 개별 화면용 용어에만 해당하는 별칭이다.
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    term_type: Mapped[str] = mapped_column(String(20), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="llm")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_prompt_version: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    first_issue_docent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("issue_docent.id"), nullable=True
    )
    source_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("dictionary_source_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_unit_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'legacy'")
    )
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=KST_NOW, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), onupdate=KST_NOW, nullable=True
    )
