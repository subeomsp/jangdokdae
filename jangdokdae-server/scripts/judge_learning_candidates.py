"""후보별 편집 판정 — 기준 문서(17-daily-selection-criteria)를 루브릭으로 LLM이 점수를 매긴다.

날짜당 1회 호출로 그날의 당일 후보 전체를 한 번에 판정하고, 결과를
`evaluation/learning/snapshots/judgments-<date>.json`에 캐시한다. 이미 판정된
날짜는 건너뛴다(--force로 재판정). 조합(역할 배정·섹터 다양성·신선도)은 LLM이
아니라 점수 모델 코드가 담당한다 — 여기서는 후보 개별 평가만 한다.

사용:
    uv run python -m scripts.judge_learning_candidates            # 모든 스냅샷
    uv run python -m scripts.judge_learning_candidates --date 2026-07-27
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

SNAPSHOT_DIR = Path("evaluation/learning/snapshots")
JUDGE_PROMPT_VERSION = "selection-judge-v1"


class CandidateJudgment(BaseModel):
    issue_id: int
    learn_value: int = Field(ge=0, le=10, description="초보자 학습 가치")
    focus_fit: int = Field(ge=0, le=10, description="핵심(오늘의 1순위 사건) 적합도")
    context_fit: int = Field(ge=0, le=10, description="맥락(시장 상태 변화) 적합도")
    discovery_fit: int = Field(ge=0, le=10, description="발견(시야 확장 배울거리) 적합도")
    reason: str = Field(description="한 문장 근거")


class DayJudgment(BaseModel):
    judgments: list[CandidateJudgment]


PROMPT = """너는 주식 초보자를 위한 하루 세 가지 학습 콘텐츠의 편집장이다.
아래 [후보 목록]의 각 항목을 세 역할 관점에서 0~10점으로 평가한다.

역할 정의:
- 핵심(focus): 그날 가장 중요한 구체적 사건. "오늘 하나만 읽는다면?"
- 맥락(context): 개별 사건 너머 시장 전체가 움직인 이유·상태(지수·금리·물가·수급·유가).
  제도·규제 "발표"는 시장 영향이 있어도 상태가 아니라 사건이므로 맥락 적합도는 낮다.
- 발견(discovery): 초보자가 스스로 찾아보지 않을 다른 영역의 배울거리. 중요도가 낮아도
  시장의 작동 원리를 하나 배울 수 있으면 좋은 발견이다.

학습 가치(learn_value): 이 사건을 통해 시장의 작동 원리를 하나 배울 수 있는가.
실적 발표→주가, 유가→항공주 같은 인과 구조가 있으면 높고, 단순 시세 중계
("○○ 급등, 원인 미상")나 특정 종목 추종을 부추기는 구도는 낮다.

각 후보를 독립적으로 평가하고, 모든 후보에 대해 판정을 반환한다.

[날짜] {date}

[후보 목록]
{candidates}"""


def _llm():
    from langchain_google_vertexai import ChatVertexAI

    from app.config import settings

    return ChatVertexAI(
        model=settings.vertex_model,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=0,
        max_retries=2,
    ).with_structured_output(DayJudgment)


async def judge_snapshot(snapshot_path: Path, force: bool) -> Path | None:
    snapshot = json.loads(snapshot_path.read_text())
    day = snapshot["learning_date"]
    out_path = SNAPSHOT_DIR / f"judgments-{day}.json"
    if out_path.exists() and not force:
        return None

    fresh = [
        c for c in snapshot["candidates"] if c["run_date"] == day
    ]
    if not fresh:
        return None
    lines = [
        f"- issue_id={c['issue_id']} | scope={c['scope']} | frame={c['frame']} | "
        f"섹터={','.join(c['sector_names']) or '없음'}\n"
        f"  제목: {c['title']}\n  요약: {c['hook']}"
        for c in fresh
    ]
    prompt = PROMPT.format(date=day, candidates="\n".join(lines))
    result: DayJudgment = await _llm().ainvoke(prompt)

    valid_ids = {c["issue_id"] for c in fresh}
    judged_ids = {j.issue_id for j in result.judgments}
    missing = valid_ids - judged_ids
    payload = {
        "prompt_version": JUDGE_PROMPT_VERSION,
        "learning_date": day,
        "judged_count": len(judged_ids & valid_ids),
        "missing_issue_ids": sorted(missing),
        "judgments": [
            j.model_dump() for j in result.judgments if j.issue_id in valid_ids
        ],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return out_path


async def main() -> None:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="후보별 편집 판정")
    parser.add_argument("--date", action="append", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="기존 판정 덮어쓰기")
    args = parser.parse_args()

    paths = (
        [SNAPSHOT_DIR / f"selection-pool-{d.isoformat()}.json" for d in args.date]
        if args.date
        else sorted(SNAPSHOT_DIR.glob("selection-pool-*.json"))
    )
    for path in paths:
        written = await judge_snapshot(path, args.force)
        print(f"{path.name}: {'저장 ' + written.name if written else '건너뜀(캐시)'}")


if __name__ == "__main__":
    asyncio.run(main())
