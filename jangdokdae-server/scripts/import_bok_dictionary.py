"""한국은행 경제금융용어 800선 원문 가져오기와 화면용 설명 생성.

기본 실행은 공식 원문 전체만 안전하게 저장한다. LLM 비용이 드는 화면용 설명 생성은
``--generate``를 명시했을 때, 기존 사전이나 발행 콘텐츠에서 실제로 쓰이는 항목에
한해서 수행한다.

사용:
    uv run python scripts/import_bok_dictionary.py
    uv run python scripts/import_bok_dictionary.py --pdf /tmp/bok-800.pdf --dry-run
    uv run python scripts/import_bok_dictionary.py --generate --limit 20
    uv run python scripts/import_bok_dictionary.py --generate --limit 20 --overwrite-existing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import KST_NOW, AsyncSessionLocal
from app.db.orm_models.dictionary_source_entry import DictionarySourceEntry
from app.db.orm_models.dictionary_term import DictionaryTerm
from app.db.orm_models.issue_docent import IssueDocent
from services.analyzer.bok_dictionary import (
    BOK_PDF_URL,
    BOK_SOURCE_CODE,
    BOK_SOURCE_TITLE,
    BOK_SOURCE_URL,
    BOK_SOURCE_VERSION,
    BokDictionaryEntry,
    download_bok_pdf,
    parse_bok_dictionary,
)
from services.analyzer.dictionary_generator import (
    GROUNDED_DICTIONARY_MIN_SCORE,
    generate_verified_grounded_dictionary_draft,
    grounded_dictionary_model_name,
)

logger = logging.getLogger(__name__)
DEFAULT_PDF_PATH = Path("/tmp/jangdokdae-bok-800.pdf")


def _content_text(docent: IssueDocent) -> str:
    return " ".join(
        [
            docent.title or "",
            json.dumps(docent.hook_lines or {}, ensure_ascii=False),
            json.dumps(docent.content_heads or [], ensure_ascii=False),
        ]
    )


def _appears_in_content(alias: str, corpus: str) -> bool:
    compact = re.sub(r"[\s()\-/]", "", alias)
    if len(compact) < 3:
        return False
    if re.fullmatch(r"[A-Za-z0-9+.\- ]+", alias):
        return (
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                corpus,
                flags=re.IGNORECASE,
            )
            is not None
        )
    return alias in corpus


def select_entries(
    entries: list[BokDictionaryEntry],
    content_corpus: str,
) -> dict[str, str]:
    """현재 서비스에서 필요한 원문 항목과 선택 이유를 반환한다."""

    selected: dict[str, str] = {}
    for entry in entries:
        if any(_appears_in_content(alias, content_corpus) for alias in entry.aliases):
            selected[entry.term] = "issue_content"
    return selected


async def _load_context() -> tuple[list[DictionaryTerm], str]:
    async with AsyncSessionLocal() as db:
        dictionary_rows = list(
            (await db.execute(select(DictionaryTerm).order_by(DictionaryTerm.id))).scalars().all()
        )
        docents = list(
            (
                await db.execute(
                    select(IssueDocent).order_by(IssueDocent.id)
                )
            )
            .scalars()
            .all()
        )
    return dictionary_rows, " ".join(_content_text(docent) for docent in docents)


async def _upsert_sources(
    entries: list[BokDictionaryEntry], selected: dict[str, str]
) -> None:
    values = [
        {
            "source_code": BOK_SOURCE_CODE,
            "source_title": BOK_SOURCE_TITLE,
            "source_version": BOK_SOURCE_VERSION,
            "term": entry.term,
            "aliases": entry.aliases,
            "raw_definition": entry.raw_definition,
            "related_terms": entry.related_terms,
            "source_url": BOK_SOURCE_URL,
            "source_pdf_url": BOK_PDF_URL,
            "source_page": entry.source_page,
            "pdf_page": entry.pdf_page,
            "content_hash": entry.content_hash,
            "is_selected": entry.term in selected,
            "selection_reason": selected.get(entry.term),
        }
        for entry in entries
    ]
    async with AsyncSessionLocal() as db:
        insert = pg_insert(DictionarySourceEntry).values(values)
        await db.execute(
            insert.on_conflict_do_update(
                constraint="uq_dictionary_source_entries_source_version_term",
                set_={
                    "aliases": insert.excluded.aliases,
                    "raw_definition": insert.excluded.raw_definition,
                    "related_terms": insert.excluded.related_terms,
                    "source_url": insert.excluded.source_url,
                    "source_pdf_url": insert.excluded.source_pdf_url,
                    "source_page": insert.excluded.source_page,
                    "pdf_page": insert.excluded.pdf_page,
                    "content_hash": insert.excluded.content_hash,
                    "is_selected": insert.excluded.is_selected,
                    "selection_reason": insert.excluded.selection_reason,
                    "updated_at": KST_NOW,
                },
            )
        )
        await db.commit()


def _target_term(entry: DictionarySourceEntry, existing_by_name: dict[str, DictionaryTerm]) -> str:
    for alias in entry.aliases or []:
        existing = existing_by_name.get(alias.casefold())
        if existing is not None:
            return existing.term
    return entry.term


async def _generate_selected(
    limit: int, overwrite_existing: bool, target_term: str | None
) -> None:
    async with AsyncSessionLocal() as db:
        source_rows = list(
            (
                await db.execute(
                    select(DictionarySourceEntry)
                    .where(
                        DictionarySourceEntry.source_code == BOK_SOURCE_CODE,
                        DictionarySourceEntry.source_version == BOK_SOURCE_VERSION,
                        DictionarySourceEntry.is_selected.is_(True),
                    )
                    .order_by(DictionarySourceEntry.source_page, DictionarySourceEntry.id)
                )
            )
            .scalars()
            .all()
        )
        existing_rows = list((await db.execute(select(DictionaryTerm))).scalars().all())

    if target_term:
        target_key = target_term.casefold()
        source_rows = [
            row
            for row in source_rows
            if row.term.casefold() == target_key
            or any(alias.casefold() == target_key for alias in (row.aliases or []))
        ]
        if not source_rows:
            raise ValueError(f"selected source term not found: {target_term}")

    existing_by_name = {row.term.casefold(): row for row in existing_rows}
    generated = skipped = rejected = failed = 0
    for source in source_rows:
        if limit > 0 and generated + rejected + failed >= limit:
            break
        target_term = _target_term(source, existing_by_name)
        existing = existing_by_name.get(target_term.casefold())
        if (
            existing is not None
            and existing.verification_status != "legacy"
            and not overwrite_existing
        ):
            skipped += 1
            continue

        try:
            result = await generate_verified_grounded_dictionary_draft(
                target_term, source.raw_definition
            )
            draft = result.final_attempt.draft
            verdict = result.final_attempt.verdict
            approved = (
                verdict.supported
                and verdict.score >= GROUNDED_DICTIONARY_MIN_SCORE
            )
            async with AsyncSessionLocal() as db:
                row = await db.scalar(
                    select(DictionaryTerm).where(DictionaryTerm.term == target_term)
                )
                if row is None:
                    row = DictionaryTerm(
                        term=target_term,
                        aliases=source.aliases,
                        term_type=draft.term_type,
                        definition=draft.definition,
                        example=draft.example,
                        source=BOK_SOURCE_CODE,
                        status="approved" if approved else "candidate",
                        model_name=grounded_dictionary_model_name(),
                        source_entry_id=source.id,
                        source_unit_index=0,
                        source_url=source.source_url,
                        source_page=source.source_page,
                        is_ai_generated=True,
                        verification_status="verified" if approved else "rejected",
                        quality_score=verdict.score,
                    )
                    db.add(row)
                elif approved:
                    row.aliases = source.aliases
                    row.term_type = draft.term_type
                    row.definition = draft.definition
                    row.example = draft.example
                    row.source = BOK_SOURCE_CODE
                    row.status = "approved"
                    row.model_name = grounded_dictionary_model_name()
                    row.source_entry_id = source.id
                    row.source_unit_index = 0
                    row.source_url = source.source_url
                    row.source_page = source.source_page
                    row.is_ai_generated = True
                    row.verification_status = "verified"
                    row.quality_score = verdict.score
                await db.commit()
            if approved:
                generated += 1
                print(f"[verified {verdict.score}] {target_term}", flush=True)
            else:
                rejected += 1
                print(f"[rejected {verdict.score}] {target_term}: {verdict.reason}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.exception("grounded dictionary generation failed term=%s", target_term)
            print(f"[failed] {target_term}: {exc}", flush=True)

    print(
        f"생성 요약: verified={generated} rejected={rejected} "
        f"skipped_existing={skipped} failed={failed}",
        flush=True,
    )


async def run(
    *,
    pdf_path: Path,
    generate: bool,
    limit: int,
    overwrite_existing: bool,
    target_term: str | None,
    dry_run: bool,
) -> None:
    if not pdf_path.exists():
        print(f"공식 PDF 다운로드: {pdf_path}", flush=True)
        download_bok_pdf(pdf_path)

    entries = parse_bok_dictionary(pdf_path)
    existing_rows, corpus = await _load_context()
    selected = select_entries(entries, corpus)
    reason_counts = {
        reason: sum(1 for value in selected.values() if value == reason)
        for reason in sorted(set(selected.values()))
    }
    print(
        f"파싱={len(entries)} 기존사전={len(existing_rows)} "
        f"선택={len(selected)} 이유={reason_counts}",
        flush=True,
    )

    if dry_run:
        for entry in entries:
            if entry.term in selected:
                print(f"[dry-run:{selected[entry.term]}] {entry.term}", flush=True)
        return

    await _upsert_sources(entries, selected)
    print(f"원문 {len(entries)}건 저장 완료", flush=True)
    if generate:
        await _generate_selected(
            limit=limit,
            overwrite_existing=overwrite_existing,
            target_term=target_term,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="한국은행 경제금융용어 800선 가져오기")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH)
    parser.add_argument("--generate", action="store_true", help="선택 용어의 화면용 설명 생성")
    parser.add_argument("--term", default=None, help="특정 용어/별칭 하나만 생성")
    parser.add_argument("--limit", type=int, default=20, help="생성·검증 시도 수. 0=무제한")
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="검증 통과한 경우 기존 LLM 정의를 출처 기반 정의로 교체",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run(
            pdf_path=args.pdf,
            generate=args.generate,
            limit=args.limit,
            overwrite_existing=args.overwrite_existing,
            target_term=args.term,
            dry_run=args.dry_run,
        )
    )
