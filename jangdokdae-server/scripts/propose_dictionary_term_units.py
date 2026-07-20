"""한국은행 복합 제목의 개별 용어 분리안을 만들고 ``proposed``로 저장한다.

이 스크립트는 제안만 생성한다. ``approved`` 전환과 화면용 설명 생성은 사람이
relationship, 대표 용어, 별칭을 검수한 뒤 별도 단계에서 수행한다.

사용:
    uv run python scripts/propose_dictionary_term_units.py --limit 8
    uv run python scripts/propose_dictionary_term_units.py \
      --term '간접금융/직접금융' \
      --term '원/위안 직거래시장'
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE, BOK_SOURCE_VERSION
from services.analyzer.dictionary_generator import grounded_dictionary_model_name
from services.analyzer.dictionary_segmentation import (
    SEGMENTATION_PROMPT_VERSION,
    has_top_level_slash,
    proposal_to_records,
    propose_term_units,
)

logger = logging.getLogger(__name__)


async def _load_targets(
    *,
    terms: list[str],
    limit: int,
    force: bool,
) -> list[DictionarySourceEntry]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(DictionarySourceEntry)
            .where(
                DictionarySourceEntry.source_code == BOK_SOURCE_CODE,
                DictionarySourceEntry.source_version == BOK_SOURCE_VERSION,
            )
            .order_by(DictionarySourceEntry.source_page, DictionarySourceEntry.id)
        )
        if terms:
            stmt = stmt.where(DictionarySourceEntry.term.in_(terms))
        if not force:
            stmt = stmt.where(DictionarySourceEntry.term_units_status == "pending")
        rows = list((await db.execute(stmt)).scalars().all())

    if terms:
        found = {row.term for row in rows}
        missing = [term for term in terms if term not in found]
        if missing:
            raise ValueError(
                "pending source terms not found; use --force only when re-proposal is intended: "
                + ", ".join(missing)
            )
    else:
        # 기본 배치는 실제 구분 가능성이 있는 괄호 밖 slash 제목부터 처리한다.
        rows = [row for row in rows if has_top_level_slash(row.term)]

    return rows[:limit] if limit > 0 else rows


async def _save_proposal(
    source_id: int,
    records: list[dict],
    *,
    force: bool,
) -> bool:
    """동시에 검수된 행을 덮어쓰지 않도록 현재 상태를 다시 확인한다."""

    async with AsyncSessionLocal() as db:
        row = await db.get(DictionarySourceEntry, source_id, with_for_update=True)
        if row is None:
            return False
        if row.term_units_status != "pending" and not force:
            return False
        if row.term_units_status == "approved":
            # 승인 데이터는 ``--force``로도 덮어쓰지 않는다.
            return False

        row.term_units = records
        row.term_units_status = "proposed"
        row.term_units_model_name = grounded_dictionary_model_name()
        row.term_units_prompt_version = SEGMENTATION_PROMPT_VERSION
        row.term_units_reviewed_at = None
        await db.commit()
        return True


async def run(
    *,
    terms: list[str],
    limit: int,
    force: bool,
    dry_run: bool,
) -> None:
    targets = await _load_targets(terms=terms, limit=limit, force=force)
    print(f"분리 제안 대상={len(targets)}", flush=True)

    proposed = skipped = failed = 0
    for source in targets:
        try:
            proposal = await propose_term_units(source.term, source.raw_definition)
            records = proposal_to_records(proposal)
            summary = ", ".join(
                f"{record['term']} aliases={record['aliases']}" for record in records
            )
            print(
                f"[proposal] {source.term} -> {proposal.relationship}: {summary}",
                flush=True,
            )
            print(f"  reason: {proposal.reason}", flush=True)
            if dry_run:
                skipped += 1
                continue
            saved = await _save_proposal(source.id, records, force=force)
            if saved:
                proposed += 1
            else:
                skipped += 1
                print(f"[skipped:status-changed] {source.term}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.exception("term unit proposal failed source_id=%s", source.id)
            print(f"[failed] {source.term}: {type(exc).__name__}: {exc}", flush=True)

    print(
        f"제안 요약: proposed={proposed} skipped={skipped} failed={failed}",
        flush=True,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="한국은행 복합 제목 분리안 생성")
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="정확한 한국은행 원문 제목. 여러 번 지정 가능",
    )
    parser.add_argument("--limit", type=int, default=8, help="대상 수. 0=무제한")
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 proposed/rejected 항목을 다시 제안. approved는 덮어쓰지 않음",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="모델 제안과 검증까지만 실행하고 DB에는 저장하지 않음",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            terms=args.term,
            limit=args.limit,
            force=args.force,
            dry_run=args.dry_run,
        )
    )
