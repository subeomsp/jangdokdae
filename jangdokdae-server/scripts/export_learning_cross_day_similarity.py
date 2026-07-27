"""인접한 두 스냅샷 날짜 사이의 후보 임베딩 유사도를 내보낸다.

신선도(전일 발행 3개와 비교) 신호의 재료다. 각 날짜의 후보와 전날 후보 사이의
코사인 유사도를 대표 뉴스 임베딩으로 계산해 저장한다. 점수 모델이 "전일 선택
3개"와의 유사도를 조회할 때 쓴다.

사용:
    uv run python -m scripts.export_learning_cross_day_similarity
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from dotenv import load_dotenv

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
OUTPUT_PATH = SNAPSHOT_DIR / "cross-day-similarity.json"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def main() -> None:
    load_dotenv(".env")
    import os

    from sqlalchemy import create_engine, text

    snapshots = {}
    for path in sorted(SNAPSHOT_DIR.glob("selection-pool-*.json")):
        snap = json.loads(path.read_text())
        snapshots[snap["learning_date"]] = snap

    cluster_ids = sorted(
        {
            c["cluster_id"]
            for snap in snapshots.values()
            for c in snap["candidates"]
        }
    )
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT nc.id, n.embedding::text FROM news_cluster nc "
                "JOIN news n ON n.id = nc.representative_news_id "
                "WHERE nc.id = ANY(:ids)"
            ),
            {"ids": cluster_ids},
        ).all()
    engine.dispose()
    embeddings = {
        int(cluster_id): json.loads(raw) for cluster_id, raw in rows if raw
    }

    dates = sorted(snapshots)
    # 신선도 비교 창(최근 3일)의 발행분과 대조할 수 있게 3일 전까지의 쌍을 계산한다.
    result: dict[str, dict[str, dict[str, float]]] = {}
    for index, date in enumerate(dates):
        prev_dates = dates[max(0, index - 3) : index]
        if not prev_dates:
            continue
        today = snapshots[date]["candidates"]
        previous = [
            candidate
            for prev_date in prev_dates
            for candidate in snapshots[prev_date]["candidates"]
        ]
        by_today: dict[str, dict[str, float]] = {}
        for t in today:
            te = embeddings.get(t["cluster_id"])
            if te is None:
                continue
            sims = {}
            for y in previous:
                ye = embeddings.get(y["cluster_id"])
                if ye is None:
                    continue
                sims[str(y["issue_id"])] = round(_cosine(te, ye), 4)
            by_today[str(t["issue_id"])] = sims
        result[date] = by_today

    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"{len(result)}개 날짜 쌍 저장 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
