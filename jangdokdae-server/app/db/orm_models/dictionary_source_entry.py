"""공식 용어사전 원문 저장소.

화면용으로 짧게 가공한 ``dictionary_terms``와 원문을 분리해 보존한다. 같은 출처의
같은 버전은 용어당 한 행만 가지며, 원문 해시로 재수집 시 변경 여부를 추적한다.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import KST_NOW, Base


class DictionarySourceEntry(Base):
    __tablename__ = "dictionary_source_entries"
    __table_args__ = (
        UniqueConstraint(
            "source_code",
            "source_version",
            "term",
            name="uq_dictionary_source_entries_source_version_term",
        ),
        Index("ix_dictionary_source_entries_term", "term"),
        Index("ix_dictionary_source_entries_selected", "is_selected"),
        Index(
            "ix_dictionary_source_entries_term_units_status",
            "term_units_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_code: Mapped[str] = mapped_column(String(40), nullable=False)
    source_title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str] = mapped_column(String(40), nullable=False)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    raw_definition: Mapped[str] = mapped_column(Text, nullable=False)
    related_terms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # 한 원문 제목이 여러 개념을 묶는 경우 검수된 개별 용어 계획을 보관한다.
    # [{"unit_index": 0, "term": "단리", "aliases": [], "relationship": "distinct"}]
    term_units: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    term_units_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    term_units_model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    term_units_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    # 책에 인쇄된 페이지와 PDF 뷰어의 실제 페이지는 앞표지/목차 때문에 다르다.
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    pdf_page: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=KST_NOW, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), onupdate=KST_NOW, nullable=True
    )
