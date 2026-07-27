"""하루 세 콘텐츠 선택 알고리즘을 사람 라벨 골드셋과 대조한다.

각 라벨된 날짜의 스냅샷(후보 풀)에 `select_daily_candidates`를 재생해
사람이 고른 3개와의 일치율을 잰다. 게스트(관심사 없음) 시나리오 기준.

지표:
- overlap: 알고리즘 3개 ∩ 사람 3개 / 3 (역할 무관)
- role_match: 역할까지 일치한 수 / 3
- human_rank: 사람이 고른 항목이 후보 랭킹에서 몇 위였는지(중앙값 등 분석용)

사용:
    uv run python -m evaluation.learning.run_selection
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app.api.routers.learning import LearningCandidate, select_daily_candidates

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
GOLD_PATH = Path("evaluation/learning/tasks/selection_gold.jsonl")


def candidate_from_snapshot(row: dict) -> LearningCandidate:
    docent = SimpleNamespace(id=row["issue_id"], title=row["title"])
    cluster = SimpleNamespace(
        id=row["cluster_id"],
        stable_id=row.get("stable_id"),
        run_date=row["run_date"],
        is_current=row.get("is_current", False),
        importance=row.get("importance", 0.0),
    )
    analysis = SimpleNamespace(
        scope=row["scope"],
        sector_ids=row.get("sector_ids", []),
        company_ids=row.get("company_ids", []),
    )
    return LearningCandidate(docent, cluster, analysis)


def replay_day(task: dict) -> dict:
    snapshot = json.loads((SNAPSHOT_DIR / task["snapshot"]).read_text())
    rows = snapshot["candidates"]
    candidates = [candidate_from_snapshot(row) for row in rows]
    chosen = select_daily_candidates(candidates, sector_ids=set(), company_ids=set())
    algo = {role: candidate.issue_id for role, candidate in chosen}
    human = {s["role"]: s["issue_id"] for s in task["selections"]}

    algo_ids = set(algo.values())
    human_ids = set(human.values())
    rank_by_id = {row["issue_id"]: row["rank"] for row in rows}
    titles = {row["issue_id"]: row["title"] for row in rows}
    return {
        "learning_date": task["learning_date"],
        "pool_size": len(rows),
        "algo": algo,
        "human": human,
        "overlap": len(algo_ids & human_ids),
        "role_match": sum(1 for role in human if algo.get(role) == human[role]),
        "human_ranks": sorted(rank_by_id[i] for i in human_ids),
        "titles": titles,
    }


def replay_day_v2(
    task: dict,
    prev_selected: list[dict],
    similarity_all: dict,
    model: str = "v2",
) -> tuple[dict, list[dict]]:
    """점수 모델을 순차 시뮬레이션으로 재생한다. 전일 선택은 모델 자신의 결과다."""
    from evaluation.learning.scoring import select_daily_v2, select_daily_v3

    snapshot = json.loads((SNAPSHOT_DIR / task["snapshot"]).read_text())
    rows = snapshot["candidates"]
    if model == "v3":
        judgment_path = SNAPSHOT_DIR / f"judgments-{task['learning_date']}.json"
        judgments = {
            j["issue_id"]: j
            for j in json.loads(judgment_path.read_text())["judgments"]
        }
        chosen = select_daily_v3(
            rows,
            task["learning_date"],
            prev_selected,
            similarity_all.get(task["learning_date"]),
            judgments,
        )
    else:
        chosen = select_daily_v2(
            rows,
            task["learning_date"],
            prev_selected,
            similarity_all.get(task["learning_date"]),
        )
    algo = {role: row["issue_id"] for role, row in chosen}
    human = {s["role"]: s["issue_id"] for s in task["selections"]}
    algo_ids, human_ids = set(algo.values()), set(human.values())
    rank_by_id = {row["issue_id"]: row["rank"] for row in rows}
    result = {
        "learning_date": task["learning_date"],
        "pool_size": len(rows),
        "algo": algo,
        "human": human,
        "overlap": len(algo_ids & human_ids),
        "role_match": sum(1 for role in human if algo.get(role) == human[role]),
        "human_ranks": sorted(rank_by_id[i] for i in human_ids),
        "titles": {row["issue_id"]: row["title"] for row in rows},
    }
    return result, [row for _, row in chosen]


def main() -> None:
    parser = argparse.ArgumentParser(description="선택 알고리즘 vs 사람 라벨 재현 평가")
    parser.add_argument("--verbose", action="store_true", help="날짜별 선택 제목 출력")
    parser.add_argument(
        "--model",
        choices=["current", "v2", "v3"],
        default="current",
        help="current=운영 휴리스틱, v2=코드 신호 점수, v3=LLM 편집 판정 결합",
    )
    args = parser.parse_args()

    tasks = [
        json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    tasks.sort(key=lambda t: t["learning_date"])
    if args.model in ("v2", "v3"):
        similarity_path = SNAPSHOT_DIR / "cross-day-similarity.json"
        similarity_all = json.loads(similarity_path.read_text())
        results = []
        # 신선도 비교 창: 최근 3일 발행분(모델 자신의 선택)을 유지한다.
        recent_selected: list[list[dict]] = []
        for task in tasks:
            flattened = [row for day_rows in recent_selected for row in day_rows]
            result, day_selected = replay_day_v2(
                task, flattened, similarity_all, model=args.model
            )
            results.append(result)
            recent_selected = (recent_selected + [day_selected])[-3:]
    else:
        results = [replay_day(task) for task in tasks]

    total_overlap = sum(r["overlap"] for r in results)
    total_role = sum(r["role_match"] for r in results)
    n = len(results) * 3
    print(f"라벨된 날짜: {len(results)}일 | 게스트 시나리오")
    print(f"top-3 overlap: {total_overlap}/{n} = {total_overlap / n:.1%}")
    print(f"역할까지 일치: {total_role}/{n} = {total_role / n:.1%}")
    all_ranks = [rank for r in results for rank in r["human_ranks"]]
    print(f"사람 선택의 후보 랭킹 분포: 중앙값 {sorted(all_ranks)[len(all_ranks) // 2]}, "
          f"최소 {min(all_ranks)}, 최대 {max(all_ranks)}")
    print()
    for r in results:
        marks = []
        for role in ("focus", "context", "discovery"):
            a, h = r["algo"].get(role), r["human"].get(role)
            mark = "=" if a == h else ("~" if a in r["human"].values() else "x")
            marks.append(f"{role}:{mark}")
        print(f"{r['learning_date']}  overlap {r['overlap']}/3  ({' '.join(marks)})")
        if args.verbose:
            for role in ("focus", "context", "discovery"):
                a, h = r["algo"].get(role), r["human"].get(role)
                if a == h:
                    print(f"    {role:9s} 일치: {r['titles'].get(h, h)}")
                else:
                    print(f"    {role:9s} 사람: {r['titles'].get(h, h)}")
                    print(f"    {'':9s} 알고: {r['titles'].get(a, a)}")


if __name__ == "__main__":
    main()
