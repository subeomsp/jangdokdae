"""사람이 승인한 한국은행 쉬운 설명을 definition 골드셋에 추가한다."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from app.db.orm_models.dictionary_term import DictionaryTerm
from app.db.orm_models.issue_docent import IssueDocent as _IssueDocent  # noqa: F401
from evaluation.dictionary.definition_schemas import (
    DefinitionEvalTask,
    ReferenceDefinition,
    load_definition_tasks,
)
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE
from services.analyzer.dictionary_generator import GROUNDED_DICTIONARY_MIN_SCORE

KST = ZoneInfo("Asia/Seoul")
DEFAULT_GOLD_PATH = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "dictionary"
    / "tasks"
    / "definition_gold.jsonl"
)


def _task_from_rows(
    row: DictionaryTerm,
    source: DictionarySourceEntry,
    *,
    task_id: str,
    reviewed_at: datetime,
    batch_tag: str,
) -> DefinitionEvalTask:
    if (
        row.status != "approved"
        or row.source != BOK_SOURCE_CODE
        or row.verification_status != "verified"
        or (row.quality_score or 0) < GROUNDED_DICTIONARY_MIN_SCORE
        or row.source_unit_index is None
    ):
        raise ValueError(f"{row.term}: not an approved grounded definition")
    return DefinitionEvalTask(
        id=task_id,
        label_status="approved",
        source_code="bok_800",
        source_version=source.source_version,
        source_page=source.source_page,
        pdf_page=source.pdf_page,
        source_term=source.term,
        source_unit_index=row.source_unit_index,
        term=row.term,
        aliases=list(row.aliases or []),
        raw_definition=source.raw_definition,
        content_hash=source.content_hash,
        reference=ReferenceDefinition(
            term_type=row.term_type,
            definition=row.definition,
            example=row.example,
        ),
        tags=[batch_tag, "human_reviewed"],
        reviewed_by="project-owner",
        reviewed_at=reviewed_at,
    )


async def export(terms: list[str], gold_path: Path, batch_tag: str) -> None:
    if not terms:
        raise ValueError("at least one --term is required")
    existing = load_definition_tasks(gold_path) if gold_path.exists() else []
    existing_terms = {task.term for task in existing}

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(DictionaryTerm, DictionarySourceEntry)
                    .join(
                        DictionarySourceEntry,
                        DictionaryTerm.source_entry_id == DictionarySourceEntry.id,
                    )
                    .where(DictionaryTerm.term.in_(terms))
                    .order_by(DictionaryTerm.id)
                )
            )
            .all()
        )
    found = {row.term for row, _source in rows}
    missing = [term for term in terms if term not in found]
    if missing:
        raise ValueError(f"approved definitions not found: {', '.join(missing)}")

    next_number = (
        max(int(task.id.rsplit("-", 1)[1]) for task in existing) + 1
        if existing
        else 1
    )
    reviewed_at = datetime.now(KST)
    additions: list[DefinitionEvalTask] = []
    for row, source in rows:
        if row.term in existing_terms:
            continue
        additions.append(
            _task_from_rows(
                row,
                source,
                task_id=f"bok-def-{next_number:03d}",
                reviewed_at=reviewed_at,
                batch_tag=batch_tag,
            )
        )
        next_number += 1

    gold_path.parent.mkdir(parents=True, exist_ok=True)
    if additions:
        with gold_path.open("a", encoding="utf-8") as output:
            for task in additions:
                output.write(task.model_dump_json() + "\n")
    print(
        f"설명 골드셋 추가={len(additions)} 기존={len(existing)} "
        f"전체={len(existing) + len(additions)}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="승인 쉬운 설명을 골드셋에 추가")
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--gold-path", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--batch-tag", default="definition_batch_01")
    args = parser.parse_args()
    asyncio.run(export(args.term, args.gold_path, args.batch_tag))
