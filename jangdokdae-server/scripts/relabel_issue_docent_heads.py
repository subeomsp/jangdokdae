"""issue_docent.content_heads의 head label만 현재 frame_head_specs로 재라벨 (LLM 재호출 없음).

frame_head_specs.yaml의 label/global_label 텍스트가 바뀌었을 때, 이미 생성된 콘텐츠의
content_heads에서 label만 새 스펙으로 교체한다(question·answer 등 나머지는 보존). 행의
news_analysis.frame·origin으로 frames.get_head_specs를 불러, head의 question을 키로 새 label을
매핑한다(question은 안 바뀌어 안전; 매칭 실패 시 옛 label 유지 + 경고).

frames는 import 시 현재 frame_head_specs.yaml을 로드하므로 편집본이 자동 반영된다(YAML 커밋 불필요).

사용:
    python -m scripts.relabel_issue_docent_heads                       # 오늘 생성분 dry-run
    python -m scripts.relabel_issue_docent_heads --apply               # 오늘 생성분 실제 UPDATE
    python -m scripts.relabel_issue_docent_heads --date 2026-06-23     # 특정 생성일자
    python -m scripts.relabel_issue_docent_heads --all --apply         # 전체 issue_docent
"""

import argparse
import asyncio
import json
from datetime import date as date_cls

from sqlalchemy import text

from app.db.base import AsyncSessionLocal
from services.analyzer import frames


def _relabel(content_heads: list[dict], frame: str, origin: str) -> tuple[list[dict], list[tuple]]:
    """content_heads의 label만 새 스펙으로 교체. (새 heads, [(old, new)] 변경목록) 반환."""
    try:
        specs = frames.get_head_specs(frame, origin)
    except KeyError:
        return content_heads, []  # 알 수 없는 frame — 건드리지 않음
    q2label = {s["question"]: s["label"] for s in specs}
    new_heads: list[dict] = []
    changes: list[tuple] = []
    for h in content_heads:
        old = h.get("label")
        new = q2label.get(h.get("question"), old)  # question 매칭 실패 시 옛 label 유지
        if new != old:
            changes.append((old, new))
        new_heads.append({**h, "label": new})
    return new_heads, changes


async def _run(apply: bool, date: str | None, all_rows: bool) -> None:
    where = "" if all_rows else "WHERE d.created_at::date = :d"
    params: dict = {} if all_rows else {"d": date_cls.fromisoformat(date)}
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT d.id, d.cluster_id, na.frame, na.origin, d.content_heads "
                    "FROM issue_docent d JOIN news_analysis na ON na.cluster_id = d.cluster_id "
                    f"{where} ORDER BY d.id"
                ),
                params,
            )
        ).mappings().all()

        changed = 0
        unmatched = 0
        for r in rows:
            heads = r["content_heads"] or []
            new_heads, changes = _relabel(heads, r["frame"], r["origin"])
            # question 매칭 안 된 head(스펙 불일치) 감지
            specs = frames.get_head_specs(r["frame"], r["origin"]) if r["frame"] in frames.FRAMES else []
            spec_qs = {s["question"] for s in specs}
            miss = [h.get("label") for h in heads if h.get("question") not in spec_qs]
            if miss:
                unmatched += 1
                print(f"  [경고] cluster={r['cluster_id']} question 미매칭 head={miss}")
            if not changes:
                continue
            changed += 1
            pairs = " | ".join(f"'{o}'→'{n}'" for o, n in changes)
            print(f"cluster={r['cluster_id']} ({r['frame']}/{r['origin']}): {pairs}")
            if apply:
                await db.execute(
                    text("UPDATE issue_docent SET content_heads = CAST(:ch AS jsonb) WHERE id = :id"),
                    {"ch": json.dumps(new_heads, ensure_ascii=False), "id": r["id"]},
                )
        if apply:
            await db.commit()
    mode = "적용 완료" if apply else "DRY-RUN (쓰기 없음)"
    print(f"\n[{mode}] 대상 {len(rows)}행 중 label 변경 {changed}행 (question 미매칭 {unmatched}행)")


def main() -> None:
    parser = argparse.ArgumentParser(description="issue_docent content_heads label 재라벨")
    parser.add_argument("--apply", action="store_true", help="실제 UPDATE 수행(미지정 시 dry-run)")
    parser.add_argument("--date", default="2026-06-23", help="created_at 일자 필터(기본 2026-06-23)")
    parser.add_argument("--all", action="store_true", help="날짜 필터 없이 전체 issue_docent")
    args = parser.parse_args()
    asyncio.run(_run(args.apply, args.date, args.all))


if __name__ == "__main__":
    main()
