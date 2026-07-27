"""오늘의 학습 후보 풀을 날짜별 스냅샷으로 내보낸다.

하루 세 콘텐츠 선택 기준 골드셋(P0-2)의 재료다. 각 날짜에 대해 "그날 API가 봤을
후보 풀"을 `_load_candidates(as_of=그날 끝)`으로 재구성해 JSON으로 저장한다.
저장된 스냅샷은 DB 보관 정책과 무관하게 평가를 재현할 수 있게 한다.

사용:
    uv run python -m scripts.export_learning_selection_snapshots --all
    uv run python -m scripts.export_learning_selection_snapshots --date 2026-07-27
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import select

from app.api.routers.learning import _load_candidates
from app.db.base import AsyncSessionLocal
from app.db.orm_models.news_cluster import NewsCluster
from app.db.orm_models.sector import Sector

DEFAULT_OUTPUT_DIR = Path("evaluation/learning/snapshots")
SNAPSHOT_VERSION = 1


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59))


async def _candidate_dates(db) -> list[date]:
    rows = (await db.execute(select(NewsCluster.run_date).distinct())).scalars().all()
    return sorted({value for value in rows if value is not None})


async def export_snapshots(
    days: list[date] | None, output_dir: Path, include_all: bool
) -> list[Path]:
    written: list[Path] = []
    async with AsyncSessionLocal() as db:
        sector_names = {
            row.id: row.name_ko
            for row in (await db.execute(select(Sector))).scalars().all()
        }
        targets = days or []
        if include_all:
            targets = await _candidate_dates(db)
        for day in targets:
            candidates = await _load_candidates(db, as_of=_end_of_day(day))
            if not candidates:
                continue
            snapshot = {
                "snapshot_version": SNAPSHOT_VERSION,
                "learning_date": day.isoformat(),
                "as_of": _end_of_day(day).isoformat(),
                "window_days": 7,
                "candidates": [
                    {
                        # 리스트 순서가 API의 랭킹 순서다(최신 실행일→중요도).
                        "rank": rank,
                        "issue_id": candidate.issue_id,
                        "cluster_id": int(candidate.cluster.id),
                        "stable_id": getattr(candidate.cluster, "stable_id", None),
                        "run_date": candidate.cluster.run_date.isoformat(),
                        "is_current": bool(getattr(candidate.cluster, "is_current", False)),
                        "importance": candidate.importance,
                        "scope": str(getattr(candidate.analysis, "scope", "")),
                        "sector_ids": sorted(candidate.sector_ids),
                        "sector_names": [
                            sector_names.get(sector_id, str(sector_id))
                            for sector_id in sorted(candidate.sector_ids)
                        ],
                        "company_ids": sorted(candidate.company_ids),
                        "title": str(candidate.docent.title),
                        "hook": str(
                            (getattr(candidate.docent, "hook_lines", None) or {}).get(
                                "neutral", ""
                            )
                        ),
                        "created_at": candidate.docent.created_at.isoformat(),
                    }
                    for rank, candidate in enumerate(candidates, start=1)
                ],
            }
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"selection-pool-{day.isoformat()}.json"
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )
            written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="오늘의 학습 후보 풀 스냅샷 내보내기")
    parser.add_argument("--date", action="append", type=date.fromisoformat, default=None)
    parser.add_argument("--all", action="store_true", help="후보가 있는 모든 실행일")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if not args.date and not args.all:
        parser.error("--date 또는 --all 중 하나는 필요합니다")

    written = asyncio.run(export_snapshots(args.date, args.output_dir, args.all))
    for path in written:
        print(path)
    print(f"{len(written)}개 스냅샷 저장")


if __name__ == "__main__":
    main()
