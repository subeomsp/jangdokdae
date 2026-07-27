"""하루 세 콘텐츠 점수 모델 v1 — docs/design/17-daily-selection-criteria.md의 코드 번역.

오프라인 검증용이다. 골드셋 재현 평가에서 베이스라인 대비 개선이 확인되기 전에는
API에 연결하지 않는다.

입력은 스냅샷 v2의 후보 dict 리스트다(size·source_count·frame 포함).
"""

from __future__ import annotations

import math

# 기준 문서 §3.2 — 최근 발행분과 임베딩이 이 값 이상 비슷하면 무전개 반복으로 본다.
# 라벨 데이터에서 사람의 반복 회피 기억은 하루보다 길어(사이드카류를 며칠간 회피)
# 비교 창을 최근 3일 발행분으로 둔다.
NOVELTY_SIM_THRESHOLD = 0.70
NOVELTY_HARD_THRESHOLD = 0.82
NOVELTY_PENALTY_WEIGHT = 30.0
# 기준 문서 §2 — 맥락은 시장의 "상태 변화"(시세·흐름)를 제도 발표보다 우선한다.
CONTEXT_STATE_FRAMES = {"PRICE", "TREND"}


def impact_score(candidate: dict) -> float:
    """파급력(보조 신호): 보도량과 출처 다양성. 기준 문서 §3.1 — 과대 반영 금지."""
    return math.log1p(candidate.get("size", 0)) + math.log1p(
        candidate.get("source_count", 0)
    )


def novelty_penalty(
    candidate: dict,
    prev_selected: list[dict],
    similarity: dict[str, dict[str, float]] | None,
) -> float:
    """전일 발행 3개와의 반복 페널티. 같은 stable 주제는 사실상 제외 수준."""
    if not prev_selected:
        return 0.0
    prev_stable = {p.get("stable_id") for p in prev_selected} - {None}
    if candidate.get("stable_id") in prev_stable:
        return 100.0
    if not similarity:
        return 0.0
    sims = similarity.get(str(candidate["issue_id"]), {})
    max_sim = max(
        (sims.get(str(p["issue_id"]), 0.0) for p in prev_selected), default=0.0
    )
    if max_sim >= NOVELTY_HARD_THRESHOLD:
        return 100.0
    return NOVELTY_PENALTY_WEIGHT * max(0.0, max_sim - NOVELTY_SIM_THRESHOLD)


def base_score(
    candidate: dict,
    prev_selected: list[dict],
    similarity: dict[str, dict[str, float]] | None,
) -> float:
    return impact_score(candidate) - novelty_penalty(candidate, prev_selected, similarity)


def select_daily_v3(
    rows: list[dict],
    learning_date: str,
    prev_selected: list[dict],
    similarity: dict[str, dict[str, float]] | None,
    judgments: dict[int, dict],
) -> list[tuple[str, dict]]:
    """LLM 편집 판정(역할 적합·학습 가치) + 코드 조합 규칙(신선도·섹터 다양성).

    judgments: issue_id → {learn_value, focus_fit, context_fit, discovery_fit}.
    판정이 없는 후보는 후순위로 밀린다(0점 취급).
    """
    fresh = [row for row in rows if row["run_date"] == learning_date]
    pool = fresh if len(fresh) >= 3 else rows

    def role_score(row: dict, fit_key: str) -> float:
        judged = judgments.get(row["issue_id"], {})
        return (
            judged.get(fit_key, 0)
            + 0.5 * judged.get("learn_value", 0)
            + 0.1 * impact_score(row)
            - novelty_penalty(row, prev_selected, similarity)
        )

    selected: list[tuple[str, dict]] = []
    used_ids: set[int] = set()

    def take(fit_key: str, candidates: list[dict]) -> dict | None:
        ranked = sorted(
            (row for row in candidates if row["issue_id"] not in used_ids),
            key=lambda row: role_score(row, fit_key),
            reverse=True,
        )
        if not ranked:
            return None
        used_ids.add(ranked[0]["issue_id"])
        return ranked[0]

    # 맥락을 먼저 확보한다 — 지수·시세형 대사건(시장 전체 + PRICE)은 맥락의 재료이고,
    # 핵심은 그것을 제외한 구체적 사건에서 고른다(기준 문서 §2 상태 vs 사건).
    context = take("context_fit", pool)
    if context is not None:
        selected.append(("context", context))

    non_index = [
        row
        for row in pool
        if not (row["scope"] == "시장 전체" and row["frame"] == "PRICE")
    ]
    focus = take("focus_fit", non_index) or take("focus_fit", pool)
    if focus is not None:
        selected.append(("focus", focus))

    used_sectors: set[int] = set()
    for _, row in selected:
        used_sectors.update(row.get("sector_ids", []))
    disjoint = [
        row
        for row in pool
        if not row.get("sector_ids")
        or used_sectors.isdisjoint(row.get("sector_ids", []))
    ]
    discovery = take("discovery_fit", disjoint) or take("discovery_fit", pool)
    if discovery is not None:
        selected.append(("discovery", discovery))
    return selected


def select_daily_v2(
    rows: list[dict],
    learning_date: str,
    prev_selected: list[dict],
    similarity: dict[str, dict[str, float]] | None,
) -> list[tuple[str, dict]]:
    """기준 문서의 역할·조합 규칙으로 최대 3개를 고른다.

    반환: [(role, candidate_dict)] — focus, context, discovery 순.
    """
    # §전제 — 사람 라벨 33/33이 당일 후보였다. 당일 후보가 3개 미만일 때만 이월을 쓴다.
    fresh = [row for row in rows if row["run_date"] == learning_date]
    pool = fresh if len(fresh) >= 3 else rows
    scored = sorted(
        pool,
        key=lambda row: base_score(row, prev_selected, similarity),
        reverse=True,
    )

    selected: list[tuple[str, dict]] = []
    used_ids: set[int] = set()

    def take(rows_in_order: list[dict]) -> dict | None:
        for row in rows_in_order:
            if row["issue_id"] not in used_ids:
                used_ids.add(row["issue_id"])
                return row
        return None

    # 핵심 — 그날 가장 중요한 구체적 사건: 종합 점수 1위.
    focus = take(scored)
    if focus is not None:
        selected.append(("focus", focus))

    # 맥락 — 시장 전체 범위 중 상태 프레임(시세·흐름) 우선, 없으면 시장 전체 아무거나.
    market = [row for row in scored if row["scope"] == "시장 전체"]
    market_state = [row for row in market if row["frame"] in CONTEXT_STATE_FRAMES]
    context = take(market_state) or take(market) or take(scored)
    if context is not None:
        selected.append(("context", context))

    # 발견 — 앞의 둘과 섹터가 겹치지 않는 다른 영역.
    used_sectors: set[int] = set()
    for _, row in selected:
        used_sectors.update(row.get("sector_ids", []))
    disjoint = [
        row
        for row in scored
        if not row.get("sector_ids")
        or used_sectors.isdisjoint(row.get("sector_ids", []))
    ]
    discovery = take(disjoint) or take(scored)
    if discovery is not None:
        selected.append(("discovery", discovery))

    return selected
