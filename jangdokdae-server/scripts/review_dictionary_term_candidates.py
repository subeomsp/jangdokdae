"""사람이 검수한 한국은행 쉬운 설명 후보를 승인한다.

정확한 개별 용어를 명시해야 하며, 원문 연결과 90점 품질 게이트를 다시 확인한다.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from app.db.orm_models.dictionary_term import DictionaryTerm
from app.db.orm_models.issue_docent import IssueDocent as _IssueDocent  # noqa: F401
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE
from services.analyzer.dictionary_generator import (
    GROUNDED_DICTIONARY_MIN_SCORE,
    DictionaryDraft,
    validate_grounded_draft,
)


def _approval_problems(
    row: DictionaryTerm,
    source: DictionarySourceEntry | None,
) -> list[str]:
    problems: list[str] = []
    if row.status != "candidate":
        problems.append(f"status:{row.status}")
    if row.source != BOK_SOURCE_CODE:
        problems.append(f"source:{row.source}")
    if row.verification_status != "verified":
        problems.append(f"verification:{row.verification_status}")
    if (row.quality_score or 0) < GROUNDED_DICTIONARY_MIN_SCORE:
        problems.append(f"quality_score:{row.quality_score}")
    if not row.generation_prompt_version:
        problems.append("missing_prompt_version")
    if source is None:
        problems.append("missing_source_entry")
        return problems
    if source.term_units_status != "approved":
        problems.append(f"term_units_status:{source.term_units_status}")
    if row.source_unit_index is None:
        problems.append("missing_source_unit_index")
    else:
        records = [
            record
            for record in source.term_units
            if int(record.get("unit_index", -1)) == row.source_unit_index
        ]
        if len(records) != 1:
            problems.append("source_unit_not_found")
        else:
            record = records[0]
            if record.get("term") != row.term:
                problems.append("source_unit_term_mismatch")
            if list(record.get("aliases") or []) != list(row.aliases or []):
                problems.append("source_unit_alias_mismatch")

    draft = DictionaryDraft(
        term_type=row.term_type,
        definition=row.definition,
        example=row.example,
    )
    problems.extend(validate_grounded_draft(source.raw_definition, draft))
    return problems


async def approve(terms: list[str]) -> None:
    if not terms:
        raise ValueError("at least one --term is required")

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(DictionaryTerm)
                    .where(DictionaryTerm.term.in_(terms))
                    .order_by(DictionaryTerm.id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        found = {row.term for row in rows}
        missing = [term for term in terms if term not in found]
        if missing:
            raise ValueError(f"dictionary candidates not found: {', '.join(missing)}")

        sources_by_id: dict[int, DictionarySourceEntry] = {}
        source_ids = {
            row.source_entry_id for row in rows if row.source_entry_id is not None
        }
        if source_ids:
            source_rows = list(
                (
                    await db.execute(
                        select(DictionarySourceEntry).where(
                            DictionarySourceEntry.id.in_(source_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            sources_by_id = {source.id: source for source in source_rows}

        all_problems: list[str] = []
        for row in rows:
            problems = _approval_problems(
                row,
                sources_by_id.get(row.source_entry_id),
            )
            all_problems.extend(f"{row.term}:{problem}" for problem in problems)
        if all_problems:
            raise ValueError("candidate approval blocked: " + ", ".join(all_problems))

        for row in rows:
            row.status = "approved"
        await db.commit()

    for row in rows:
        print(f"[approved:{row.quality_score}] {row.term}", flush=True)
    print(f"승인 요약: approved={len(rows)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="검수된 경제용어 설명 후보 승인")
    parser.add_argument("--term", action="append", default=[])
    args = parser.parse_args()
    asyncio.run(approve(args.term))
