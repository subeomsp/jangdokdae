"""v4 편집 판정 — 역할 점수에 무전개 반복·발견 설명 깊이를 함께 판정한다.

기존 v3처럼 날짜당 한 번만 호출한다. 최근 7일간 모델이 실제로 선택한 항목을 같은
프롬프트에 넣어, 별도 신선도 LLM 호출을 늘리지 않고 후보별 반복 여부를 판정한다.

사용:
    uv run python -m scripts.judge_learning_candidates_v4
    uv run python -m scripts.judge_learning_candidates_v4 --force
    uv run python -m scripts.judge_learning_candidates_v4 \
      --output-picks evaluation/learning/v4-picks.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from evaluation.learning.scoring import select_daily_v4
from services.learning_editorial import (
    HISTORY_DAYS,
    JUDGE_PROMPT_VERSION,
    DayJudgmentV4,
    judge_candidates,
)

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
GOLD_PATH = Path("evaluation/learning/tasks/selection_gold.jsonl")
SIMILARITY_PATH = SNAPSHOT_DIR / "cross-day-similarity.json"


def _cached_payload(
    path: Path,
    compared_ids: list[int],
    candidate_ids: list[int],
) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    if payload.get("prompt_version") != JUDGE_PROMPT_VERSION:
        return None
    if payload.get("compared_issue_ids") != compared_ids:
        return None
    if payload.get("candidate_issue_ids") != candidate_ids:
        return None
    try:
        parsed = DayJudgmentV4.model_validate(
            {"judgments": payload.get("judgments", [])}
        )
    except ValueError:
        return None
    if [item.issue_id for item in parsed.judgments] != candidate_ids:
        return None
    previous_ids = set(compared_ids)
    if any(
        set(item.matched_previous_issue_ids) - previous_ids
        for item in parsed.judgments
    ):
        return None
    return payload


async def judge_snapshot(
    snapshot_path: Path,
    previous: list[dict],
    *,
    force: bool,
) -> tuple[Path, dict, bool]:
    snapshot = json.loads(snapshot_path.read_text())
    day = snapshot["learning_date"]
    out_path = SNAPSHOT_DIR / f"judgments-v4-{day}.json"
    compared_ids = [candidate["issue_id"] for candidate in previous]
    fresh = [
        candidate
        for candidate in snapshot["candidates"]
        if candidate["run_date"] == day
    ]
    candidate_ids = [candidate["issue_id"] for candidate in fresh]
    if not force:
        cached = _cached_payload(out_path, compared_ids, candidate_ids)
        if cached is not None:
            return out_path, cached, False

    if not fresh:
        raise RuntimeError(f"{day}: 당일 후보가 없습니다")

    judgments, repair_attempted = await judge_candidates(day, fresh, previous)

    payload = {
        "prompt_version": JUDGE_PROMPT_VERSION,
        "learning_date": day,
        "history_days": HISTORY_DAYS,
        "compared_issue_ids": compared_ids,
        "candidate_issue_ids": candidate_ids,
        "judged_count": len(judgments),
        "repair_attempted": repair_attempted,
        "judgments": [item.model_dump() for item in judgments],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return out_path, payload, True


def _tasks() -> list[dict]:
    tasks = [
        json.loads(line)
        for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    return sorted(tasks, key=lambda task: task["learning_date"])


async def run(force: bool, target_dates: set[str] | None) -> list[dict]:
    similarity_all = json.loads(SIMILARITY_PATH.read_text())
    recent_selected: list[list[dict]] = []
    picks: list[dict] = []

    tasks = _tasks()
    known_dates = {task["learning_date"] for task in tasks}
    if target_dates is not None:
        unknown_dates = target_dates - known_dates
        if unknown_dates:
            raise RuntimeError(f"골드셋에 없는 날짜입니다: {sorted(unknown_dates)}")
        last_target = max(target_dates)
        tasks = [task for task in tasks if task["learning_date"] <= last_target]

    for task in tasks:
        day = task["learning_date"]
        previous = [candidate for selected in recent_selected for candidate in selected]
        snapshot_path = SNAPSHOT_DIR / task["snapshot"]
        out_path = SNAPSHOT_DIR / f"judgments-v4-{day}.json"
        should_generate = target_dates is None or day in target_dates

        if should_generate:
            _, payload, written = await judge_snapshot(
                snapshot_path,
                previous,
                force=force,
            )
            print(f"{day}: {'저장' if written else '건너뜀(캐시)'} {out_path.name}")
        else:
            compared_ids = [candidate["issue_id"] for candidate in previous]
            snapshot = json.loads(snapshot_path.read_text())
            candidate_ids = [
                candidate["issue_id"]
                for candidate in snapshot["candidates"]
                if candidate["run_date"] == day
            ]
            payload = _cached_payload(out_path, compared_ids, candidate_ids)
            if payload is None:
                raise RuntimeError(
                    f"{day}: 이후 날짜 재생에 필요한 유효한 v4 캐시가 없습니다. "
                    "--date 없이 처음부터 생성하세요."
                )

        judgments = {
            item["issue_id"]: item for item in payload["judgments"]
        }
        snapshot = json.loads(snapshot_path.read_text())
        chosen = select_daily_v4(
            snapshot["candidates"],
            day,
            previous,
            similarity_all.get(day),
            judgments,
        )
        day_selected = [
            {**candidate, "_selected_on": day} for _, candidate in chosen
        ]
        recent_selected = (recent_selected + [day_selected])[-HISTORY_DAYS:]
        picks.append(
            {
                "date": day,
                "items": [
                    {
                        "role": role,
                        "issue_id": candidate["issue_id"],
                        "title": candidate["title"],
                        "hook": candidate["hook"],
                        "scope": candidate["scope"],
                        "sectors": candidate["sector_names"],
                        "judge_reason": judgments[candidate["issue_id"]]["reason"],
                        "topic_overlap": judgments[candidate["issue_id"]][
                            "topic_overlap"
                        ],
                        "has_new_development": judgments[candidate["issue_id"]][
                            "has_new_development"
                        ],
                        "explains_why": judgments[candidate["issue_id"]]["explains_why"],
                    }
                    for role, candidate in chosen
                ],
            }
        )
    return picks


async def main() -> None:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="v4 후보별 편집·신선도 판정")
    parser.add_argument("--date", action="append", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="유효한 기존 캐시도 덮어쓰기")
    parser.add_argument("--output-picks", type=Path, default=None)
    args = parser.parse_args()

    target_dates = (
        {value.isoformat() for value in args.date} if args.date is not None else None
    )
    picks = await run(args.force, target_dates)
    if args.output_picks is not None:
        args.output_picks.parent.mkdir(parents=True, exist_ok=True)
        args.output_picks.write_text(
            json.dumps(picks, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"검토 입력 저장 {args.output_picks}")


if __name__ == "__main__":
    asyncio.run(main())
