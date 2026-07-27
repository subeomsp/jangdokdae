"""라벨링 UI에서 내보낸 선택 라벨을 골드셋(JSONL)으로 저장한다.

입력은 `selection-labels-v1` 스키마 JSON이며, 각 날짜를 스냅샷과 대조해
issue_id가 실제 후보 풀에 존재하는지 검증한 뒤 저장한다. 같은 날짜가 이미
골드셋에 있으면 새 라벨로 교체한다(재라벨링 허용).

사용:
    uv run python -m scripts.import_learning_selection_labels labels.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
GOLD_PATH = Path("evaluation/learning/tasks/selection_gold.jsonl")
VALID_ROLES = {"focus", "context", "discovery"}


def import_labels(labels_path: Path, gold_path: Path = GOLD_PATH) -> list[str]:
    payload = json.loads(labels_path.read_text())
    if payload.get("schema") != "selection-labels-v1":
        raise SystemExit(f"지원하지 않는 스키마: {payload.get('schema')}")

    existing: dict[str, dict] = {}
    if gold_path.exists():
        for line in gold_path.read_text().splitlines():
            if line.strip():
                task = json.loads(line)
                existing[task["learning_date"]] = task

    imported: list[str] = []
    for day in payload["days"]:
        date = day["learning_date"]
        snapshot_path = SNAPSHOT_DIR / f"selection-pool-{date}.json"
        if not snapshot_path.exists():
            raise SystemExit(f"스냅샷 없음: {snapshot_path}")
        snapshot = json.loads(snapshot_path.read_text())
        pool_ids = {c["issue_id"] for c in snapshot["candidates"]}

        selections = day["selections"]
        roles = [s["role"] for s in selections]
        if sorted(roles) != sorted(VALID_ROLES):
            raise SystemExit(f"{date}: 역할 3개(focus/context/discovery)가 아님: {roles}")
        for s in selections:
            if s["issue_id"] not in pool_ids:
                raise SystemExit(f"{date}: issue_id {s['issue_id']}가 후보 풀에 없음")

        existing[date] = {
            "id": f"sel-{date}",
            "learning_date": date,
            "snapshot": snapshot_path.name,
            "selections": sorted(selections, key=lambda s: s["role"]),
            "note": day.get("note", ""),
            "labeled_at": payload.get("labeled_at"),
            "labeled_by": "project-owner",
        }
        imported.append(date)

    gold_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(existing[date], ensure_ascii=False)
        for date in sorted(existing)
    ]
    gold_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="선택 라벨을 골드셋으로 저장")
    parser.add_argument("labels", type=Path)
    args = parser.parse_args()
    imported = import_labels(args.labels)
    print(f"{len(imported)}일치 라벨 저장: {', '.join(imported)}")
    print(f"골드셋: {GOLD_PATH}")


if __name__ == "__main__":
    main()
