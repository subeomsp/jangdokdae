"""사람이 승인한 DB 분리안을 JSONL 골드셋에 추가한다.

정확한 원문 제목을 명시해야 하며, 같은 source term은 다시 추가하지 않는다.

사용:
    uv run python -m scripts.export_dictionary_segmentation_gold --term '단리/복리'
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from evaluation.dictionary.schemas import (
    ExpectedSegmentation,
    ExpectedTermUnit,
    SegmentationEvalTask,
    load_segmentation_tasks,
)
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE, BOK_SOURCE_VERSION

KST = ZoneInfo("Asia/Seoul")
DEFAULT_GOLD_PATH = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "dictionary"
    / "tasks"
    / "segmentation_gold.jsonl"
)


def _task_from_source(
    source: DictionarySourceEntry,
    *,
    task_id: str,
    batch_tag: str,
) -> SegmentationEvalTask:
    if source.term_units_status != "approved" or not source.term_units_reviewed_at:
        raise ValueError(f"{source.term}: term units are not reviewed and approved")
    records = sorted(
        source.term_units,
        key=lambda record: int(record.get("unit_index", 0)),
    )
    relationships = {record.get("relationship") for record in records}
    if len(relationships) != 1:
        raise ValueError(f"{source.term}: inconsistent relationships")

    reviewed_at = source.term_units_reviewed_at
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=KST)
    relationship = relationships.pop()
    return SegmentationEvalTask(
        id=task_id,
        label_status="approved",
        source_code="bok_800",
        source_version=source.source_version,
        source_page=source.source_page,
        pdf_page=source.pdf_page,
        source_term=source.term,
        raw_definition=source.raw_definition,
        content_hash=source.content_hash,
        expected=ExpectedSegmentation(
            relationship=relationship,
            units=[
                ExpectedTermUnit(
                    term=str(record.get("term", "")),
                    aliases=list(record.get("aliases") or []),
                )
                for record in records
            ],
        ),
        tags=[batch_tag, str(relationship), "human_reviewed"],
        reviewed_by="project-owner",
        reviewed_at=reviewed_at,
    )


async def export(
    *,
    terms: list[str],
    gold_path: Path,
    batch_tag: str,
) -> None:
    if not terms:
        raise ValueError("at least one --term is required")
    existing = load_segmentation_tasks(gold_path)
    existing_terms = {task.source_term for task in existing}

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(DictionarySourceEntry)
                    .where(
                        DictionarySourceEntry.source_code == BOK_SOURCE_CODE,
                        DictionarySourceEntry.source_version == BOK_SOURCE_VERSION,
                        DictionarySourceEntry.term.in_(terms),
                    )
                    .order_by(DictionarySourceEntry.source_page)
                )
            )
            .scalars()
            .all()
        )

    found = {row.term for row in rows}
    missing = [term for term in terms if term not in found]
    if missing:
        raise ValueError(f"source terms not found: {', '.join(missing)}")

    next_number = max(int(task.id.rsplit("-", 1)[1]) for task in existing) + 1
    additions: list[SegmentationEvalTask] = []
    for row in rows:
        if row.term in existing_terms:
            continue
        additions.append(
            _task_from_source(
                row,
                task_id=f"bok-seg-{next_number:03d}",
                batch_tag=batch_tag,
            )
        )
        next_number += 1

    if additions:
        with gold_path.open("a", encoding="utf-8") as output:
            for task in additions:
                output.write(task.model_dump_json() + "\n")

    print(
        f"골드셋 추가={len(additions)} 기존={len(existing)} 전체={len(existing) + len(additions)}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="승인 용어 분리안을 골드셋에 추가")
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--gold-path", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--batch-tag", default="batch_01")
    args = parser.parse_args()
    asyncio.run(
        export(
            terms=args.term,
            gold_path=args.gold_path,
            batch_tag=args.batch_tag,
        )
    )
