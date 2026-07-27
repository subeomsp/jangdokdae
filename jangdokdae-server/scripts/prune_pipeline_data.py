"""파이프라인 산출 데이터를 보관 기간(기본 14일) 밖에서 정리한다.

재생성 가능한 파이프라인 데이터(news, news_cluster, news_analysis, issue_docent,
disclosures)만 대상으로 한다. 다음은 보관 기간과 무관하게 절대 지우지 않는다.

- 사전 계열 테이블 전체(dictionary_source_entries, term_units, dictionary_terms)
- 사용자·활동 테이블 전체
- `dictionary_terms.first_issue_docent_id` 또는 `user_issue_activities`가 참조하는
  issue_docent 행과, 남는 issue_docent·news_analysis가 참조하는 news_cluster 행,
  남는 news_cluster가 대표로 참조하는 news 행

기본은 dry-run으로 삭제 대상 개수만 보고한다. 실제 삭제는 --apply를 명시해야 한다.

사용:
    uv run python -m scripts.prune_pipeline_data                  # dry-run
    uv run python -m scripts.prune_pipeline_data --apply
    uv run python -m scripts.prune_pipeline_data --retention-days 14
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from utils.dates import now_kst

DEFAULT_RETENTION_DAYS = 14

# 삭제는 FK 역순: issue_docent → news_analysis → news_cluster → news → disclosures
_COUNT_AND_DELETE = [
    (
        "issue_docent",
        """
        FROM issue_docent
        WHERE created_at < :cutoff
          AND id NOT IN (
            SELECT first_issue_docent_id FROM dictionary_terms
            WHERE first_issue_docent_id IS NOT NULL
          )
          AND id NOT IN (SELECT issue_docent_id FROM user_issue_activities)
        """,
    ),
    (
        "news_analysis",
        """
        FROM news_analysis
        WHERE analyzed_at < :cutoff
          AND cluster_id NOT IN (SELECT cluster_id FROM issue_docent)
        """,
    ),
    (
        "news_cluster",
        """
        FROM news_cluster
        WHERE run_date < :cutoff_date
          AND id NOT IN (SELECT cluster_id FROM issue_docent)
          AND id NOT IN (SELECT cluster_id FROM news_analysis)
        """,
    ),
    (
        "news",
        """
        FROM news
        WHERE created_at < :cutoff
          AND id NOT IN (
            SELECT representative_news_id FROM news_cluster
            WHERE representative_news_id IS NOT NULL
          )
        """,
    ),
    (
        "disclosures",
        """
        FROM disclosures
        WHERE created_at < :cutoff
        """,
    ),
]


async def prune(db: AsyncSession, retention_days: int, apply: bool) -> dict[str, int]:
    cutoff = now_kst() - timedelta(days=retention_days)
    params = {"cutoff": cutoff, "cutoff_date": cutoff.date()}
    results: dict[str, int] = {}
    for table, clause in _COUNT_AND_DELETE:
        count = (await db.execute(text(f"SELECT count(*) {clause}"), params)).scalar()
        results[table] = int(count or 0)
        if apply and count:
            await db.execute(text(f"DELETE {clause}"), params)
    if apply:
        await db.commit()
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="파이프라인 데이터 보관 기간 정리")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument(
        "--apply", action="store_true", help="실제 삭제 실행(기본은 dry-run 보고)"
    )
    args = parser.parse_args()
    if args.retention_days < 7:
        # 오늘의 학습 API가 7일 창을 쓰므로 그보다 짧은 보관은 서비스를 깨뜨린다.
        parser.error("--retention-days는 7 이상이어야 합니다")

    async with AsyncSessionLocal() as db:
        results = await prune(db, args.retention_days, args.apply)

    mode = "DELETE" if args.apply else "DRY-RUN"
    print(f"[{mode}] 보관 {args.retention_days}일 기준 삭제 대상:")
    for table, count in results.items():
        print(f"  {table:16s} {count}")


if __name__ == "__main__":
    asyncio.run(main())
