"""사람이 검수한 한국은행 용어 분리안을 승인한다.

정확한 원문 제목을 명시해야 하며 ``proposed`` 상태만 승인한다. 저장 직전에 구조와
원문 근거 검사를 다시 실행한다.

사용:
    uv run python scripts/review_dictionary_term_units.py \
      --term '간접금융/직접금융' \
      --term '원/위안 직거래시장'
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE, BOK_SOURCE_VERSION
from services.analyzer.dictionary_segmentation import (
    ProposedTermUnit,
    TermUnitProposal,
    validate_term_unit_proposal,
)

KST = ZoneInfo("Asia/Seoul")


def _stored_proposal(records: list[dict]) -> TermUnitProposal:
    """DB JSONB를 다시 검증 가능한 제안 모델로 복원한다."""

    if not records:
        raise ValueError("empty term_units")
    relationships = {record.get("relationship") for record in records}
    if len(relationships) != 1:
        raise ValueError("inconsistent relationships")
    ordered = sorted(records, key=lambda record: int(record.get("unit_index", 0)))
    return TermUnitProposal(
        relationship=relationships.pop(),
        units=[
            ProposedTermUnit(
                term=str(record.get("term", "")),
                aliases=list(record.get("aliases") or []),
            )
            for record in ordered
        ],
        reason="사람이 검수한 저장 제안",
    )


async def approve(terms: list[str]) -> None:
    if not terms:
        raise ValueError("at least one --term is required")

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
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        found = {row.term for row in rows}
        missing = [term for term in terms if term not in found]
        if missing:
            raise ValueError(f"source terms not found: {', '.join(missing)}")

        for row in rows:
            if row.term_units_status != "proposed":
                raise ValueError(
                    f"{row.term}: expected proposed, got {row.term_units_status}"
                )
            proposal = _stored_proposal(row.term_units)
            problems = validate_term_unit_proposal(
                row.term,
                row.raw_definition,
                proposal,
            )
            if problems:
                raise ValueError(f"{row.term}: invalid proposal: {', '.join(problems)}")

        reviewed_at = datetime.now(KST).replace(tzinfo=None)
        for row in rows:
            row.term_units_status = "approved"
            row.term_units_reviewed_at = reviewed_at
        await db.commit()

    for row in rows:
        print(f"[approved] {row.term}: {row.term_units}", flush=True)
    print(f"승인 요약: approved={len(rows)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="검수된 한국은행 용어 분리안 승인")
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="정확한 한국은행 원문 제목. 여러 번 지정 가능",
    )
    args = parser.parse_args()
    asyncio.run(approve(args.term))
