"""기존 issue_docent의 market_ids/sector_ids/company_ids 백필 (LLM 재호출 없음).

태깅 컬럼이 마이그레이션으로 나중에 추가돼, 이전 생성 행은 빈 배열이다. sector_ids·company_ids는
이미 news_analysis에 해소돼 있어 복사하고, market_ids는 라이브 파이프라인과 동일한
app.db.queries.resolve_market_ids로 재계산한다(종목 거래소→markets.id, 종목 없고 해외면 GLOBAL).
멱등 — 이미 채워진 행은 재계산해도 동일하므로 변경 없음.

사용:
    python -m scripts.backfill_issue_docent_tags            # dry-run (변경 미리보기, 쓰기 없음)
    python -m scripts.backfill_issue_docent_tags --apply    # 실제 UPDATE (프로덕션 쓰기)
"""

import argparse
import asyncio

from sqlalchemy import text

from app.db.base import AsyncSessionLocal
from app.db.queries import resolve_market_ids


async def _run(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT d.id, d.cluster_id, d.market_ids, d.sector_ids, d.company_ids, "
                    "na.origin, na.company_ids AS na_company, na.sector_ids AS na_sector "
                    "FROM issue_docent d JOIN news_analysis na ON na.cluster_id = d.cluster_id "
                    "ORDER BY d.id"
                )
            )
        ).mappings().all()

        changed = 0
        for r in rows:
            company_ids = list(r["na_company"] or [])
            sector_ids = list(r["na_sector"] or [])
            market_ids = await resolve_market_ids(db, company_ids, r["origin"])

            cur = (list(r["market_ids"] or []), list(r["sector_ids"] or []), list(r["company_ids"] or []))
            new = (market_ids, sector_ids, company_ids)
            if cur == new:
                continue
            changed += 1
            print(
                f"cluster={r['cluster_id']} ({r['origin']}): "
                f"market {cur[0]}→{market_ids} sector {cur[1]}→{sector_ids} company {cur[2]}→{company_ids}"
            )
            if apply:
                # asyncpg가 대상 컬럼(integer[])에서 타입을 추론하므로 파이썬 리스트를 그대로 바인딩.
                await db.execute(
                    text(
                        "UPDATE issue_docent SET market_ids = :m, sector_ids = :s, "
                        "company_ids = :c WHERE id = :id"
                    ),
                    {"m": market_ids, "s": sector_ids, "c": company_ids, "id": r["id"]},
                )
        if apply:
            await db.commit()
    mode = "적용 완료" if apply else "DRY-RUN (쓰기 없음)"
    print(f"\n[{mode}] 대상 {len(rows)}행 중 백필 {changed}행")


def main() -> None:
    parser = argparse.ArgumentParser(description="issue_docent 태깅(market/sector/company) 백필")
    parser.add_argument("--apply", action="store_true", help="실제 UPDATE 수행(미지정 시 dry-run)")
    args = parser.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
