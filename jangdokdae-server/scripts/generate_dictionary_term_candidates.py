"""승인된 개별 용어의 한국은행 원문 기반 설명 후보를 생성·검증한다.

검증을 통과해도 ``candidate``로만 저장하며 사람이 승인하기 전에는 본문에 노출되지
않는다.

사용:
    uv run python -m scripts.generate_dictionary_term_candidates \
      --term 간접금융 \
      --term 직접금융
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from app.db.orm_models.dictionary_term import DictionaryTerm
from app.db.orm_models.issue_docent import IssueDocent as _IssueDocent  # noqa: F401
from services.analyzer.bok_dictionary import BOK_SOURCE_CODE, BOK_SOURCE_VERSION
from services.analyzer.dictionary_generator import (
    GROUNDED_DICTIONARY_MIN_SCORE,
    GROUNDED_DICTIONARY_PROMPT_VERSION,
    generate_grounded_dictionary_draft,
    grounded_dictionary_model_name,
    verify_grounded_dictionary_draft,
)


@dataclass(frozen=True)
class TermUnitTarget:
    source_id: int
    source_url: str
    source_page: int
    unit_index: int
    term: str
    aliases: list[str]
    raw_definition: str


def _flatten_targets(
    sources: list[DictionarySourceEntry],
    requested_terms: list[str],
) -> list[TermUnitTarget]:
    requested = set(requested_terms)
    targets: list[TermUnitTarget] = []
    for source in sources:
        if source.term_units_status != "approved":
            continue
        for record in sorted(
            source.term_units,
            key=lambda value: int(value.get("unit_index", 0)),
        ):
            term = str(record.get("term", "")).strip()
            if term not in requested:
                continue
            targets.append(
                TermUnitTarget(
                    source_id=source.id,
                    source_url=source.source_url,
                    source_page=source.source_page,
                    unit_index=int(record.get("unit_index", 0)),
                    term=term,
                    aliases=list(record.get("aliases") or []),
                    raw_definition=source.raw_definition,
                )
            )

    found = [target.term for target in targets]
    missing = [term for term in requested_terms if term not in found]
    duplicates = {term for term in found if found.count(term) > 1}
    if missing:
        raise ValueError(f"approved term units not found: {', '.join(missing)}")
    if duplicates:
        raise ValueError(f"duplicate approved term units: {', '.join(sorted(duplicates))}")
    return targets


async def _load_targets(terms: list[str]) -> list[TermUnitTarget]:
    if not terms:
        raise ValueError("at least one --term is required")
    async with AsyncSessionLocal() as db:
        sources = list(
            (
                await db.execute(
                    select(DictionarySourceEntry)
                    .where(
                        DictionarySourceEntry.source_code == BOK_SOURCE_CODE,
                        DictionarySourceEntry.source_version == BOK_SOURCE_VERSION,
                        DictionarySourceEntry.term_units_status == "approved",
                    )
                    .order_by(DictionarySourceEntry.source_page)
                )
            )
            .scalars()
            .all()
        )
    return _flatten_targets(sources, terms)


async def _is_already_published(term: str) -> bool:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(DictionaryTerm).where(DictionaryTerm.term == term))
    return bool(
        row
        and row.status == "approved"
        and row.source == BOK_SOURCE_CODE
        and row.verification_status == "verified"
    )


async def _save_candidate(
    target: TermUnitTarget,
    draft,
    verdict,
    *,
    prompt_version: str,
) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(
            select(DictionaryTerm)
            .where(DictionaryTerm.term == target.term)
            .with_for_update()
        )
        if (
            row
            and row.status == "approved"
            and row.source == BOK_SOURCE_CODE
            and row.verification_status == "verified"
        ):
            return
        if row is None:
            row = DictionaryTerm(
                term=target.term,
                term_type=draft.term_type,
                definition=draft.definition,
                example=draft.example,
                source=BOK_SOURCE_CODE,
                status="candidate",
            )
            db.add(row)

        row.aliases = target.aliases
        row.term_type = draft.term_type
        row.definition = draft.definition
        row.example = draft.example
        row.source = BOK_SOURCE_CODE
        row.status = "candidate"
        row.model_name = grounded_dictionary_model_name()
        row.generation_prompt_version = prompt_version
        row.source_entry_id = target.source_id
        row.source_unit_index = target.unit_index
        row.source_url = target.source_url
        row.source_page = target.source_page
        row.is_ai_generated = True
        row.verification_status = (
            "verified"
            if verdict.supported and verdict.score >= GROUNDED_DICTIONARY_MIN_SCORE
            else "rejected"
        )
        row.quality_score = verdict.score
        await db.commit()


async def run(terms: list[str], review_feedback: str | None = None) -> None:
    if review_feedback and len(terms) != 1:
        raise ValueError("--review-feedback requires exactly one --term")
    targets = await _load_targets(terms)
    generated = skipped = failed = 0
    for target in targets:
        try:
            if await _is_already_published(target.term):
                skipped += 1
                print(f"[skipped:approved] {target.term}", flush=True)
                continue
            draft = await generate_grounded_dictionary_draft(
                target.term,
                target.raw_definition,
                review_feedback=review_feedback,
            )
            verdict = await verify_grounded_dictionary_draft(
                target.term,
                target.raw_definition,
                draft,
            )
            prompt_version = GROUNDED_DICTIONARY_PROMPT_VERSION
            if review_feedback:
                prompt_version += "-human-feedback"
            await _save_candidate(
                target,
                draft,
                verdict,
                prompt_version=prompt_version,
            )
            generated += 1
            print(
                f"[candidate:{verdict.score}:{'supported' if verdict.supported else 'rejected'}] "
                f"{target.term}",
                flush=True,
            )
            print(f"  definition: {draft.definition}", flush=True)
            print(f"  example: {draft.example or '(없음)'}", flush=True)
            print(f"  verifier: {verdict.reason}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[failed] {target.term}: {type(exc).__name__}: {exc}", flush=True)

    print(
        f"후보 요약: generated={generated} skipped={skipped} failed={failed}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="개별 경제용어 설명 후보 생성")
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument(
        "--review-feedback",
        default=None,
        help="한 용어의 기존 후보를 수정할 사람 검수 의견",
    )
    args = parser.parse_args()
    asyncio.run(run(args.term, review_feedback=args.review_feedback))
