"""오늘의 학습 후보 로드와 관심사 기반 최대 세 자리 재배열."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.learning import LearningRole
from app.db.orm_models.issue_docent import IssueDocent
from app.db.orm_models.news_analysis import NewsAnalysis
from app.db.orm_models.news_cluster import NewsCluster
from app.db.orm_models.sector import Sector
from utils.dates import now_kst

CANDIDATE_WINDOW_DAYS = 7
CANDIDATE_LIMIT = 60


@dataclass(frozen=True)
class LearningCandidate:
    docent: Any
    cluster: Any
    analysis: Any
    source_count: int = 0
    sector_names: tuple[str, ...] = ()

    @property
    def issue_id(self) -> int:
        return int(self.docent.id)

    @property
    def importance(self) -> float:
        return float(getattr(self.cluster, "importance", 0.0) or 0.0)

    @property
    def sector_ids(self) -> set[int]:
        return {int(value) for value in (getattr(self.analysis, "sector_ids", None) or [])}

    @property
    def company_ids(self) -> set[int]:
        return {int(value) for value in (getattr(self.analysis, "company_ids", None) or [])}

    @property
    def is_market_context(self) -> bool:
        return str(getattr(self.analysis, "scope", "")) == "시장 전체"


def matches_interests(
    candidate: LearningCandidate,
    sector_ids: set[int],
    company_ids: set[int],
) -> bool:
    return bool(candidate.sector_ids & sector_ids or candidate.company_ids & company_ids)


def _first_not_selected(
    candidates: list[LearningCandidate], selected: list[LearningCandidate]
) -> LearningCandidate | None:
    selected_ids = {candidate.issue_id for candidate in selected}
    return next(
        (candidate for candidate in candidates if candidate.issue_id not in selected_ids),
        None,
    )


def select_daily_candidates(
    candidates: list[LearningCandidate],
    *,
    sector_ids: set[int],
    company_ids: set[int],
) -> list[tuple[LearningRole, LearningCandidate]]:
    """승인 후보 안에서 관심→시장 맥락→관심 밖 발견 순으로 최대 세 개를 재배열한다."""
    if not candidates:
        return []

    ranked = candidates
    selected: list[LearningCandidate] = []

    matching = [
        candidate
        for candidate in ranked
        if matches_interests(candidate, sector_ids, company_ids)
    ]
    direct_matching = [candidate for candidate in matching if not candidate.is_market_context]
    focus = _first_not_selected(direct_matching or matching or ranked, selected)
    if focus is not None:
        selected.append(focus)

    context_matching = [
        candidate for candidate in matching if candidate.is_market_context
    ]
    all_context = [candidate for candidate in ranked if candidate.is_market_context]
    context = _first_not_selected(context_matching or all_context or ranked, selected)
    if context is not None:
        selected.append(context)

    non_matching = [
        candidate
        for candidate in ranked
        if not matches_interests(candidate, sector_ids, company_ids)
    ]
    used_sectors = set().union(*(candidate.sector_ids for candidate in selected))
    diverse_non_matching = [
        candidate
        for candidate in non_matching
        if not candidate.sector_ids or candidate.sector_ids.isdisjoint(used_sectors)
    ]
    discovery = _first_not_selected(diverse_non_matching or non_matching or ranked, selected)
    if discovery is not None:
        selected.append(discovery)

    while len(selected) < min(3, len(ranked)):
        fallback = _first_not_selected(ranked, selected)
        if fallback is None:
            break
        selected.append(fallback)

    roles: list[LearningRole] = ["focus", "context", "discovery"]
    return list(zip(roles, selected, strict=False))


async def load_candidates(
    db: AsyncSession, as_of: Any | None = None
) -> list[LearningCandidate]:
    """기준 시점 최근 후보를 로드하고 stable cluster별 최신 콘텐츠만 남긴다."""
    reference = as_of if as_of is not None else now_kst()
    since = reference - timedelta(days=CANDIDATE_WINDOW_DAYS)
    rows = (
        await db.execute(
            select(IssueDocent, NewsCluster, NewsAnalysis)
            .join(NewsCluster, IssueDocent.cluster_id == NewsCluster.id)
            .join(NewsAnalysis, IssueDocent.cluster_id == NewsAnalysis.cluster_id)
            .where(IssueDocent.created_at >= since)
            .where(IssueDocent.created_at <= reference)
            .where(NewsAnalysis.is_investment_relevant.is_(True))
            .where(NewsAnalysis.needs_review.is_(False))
            .where(func.jsonb_array_length(IssueDocent.quizzes) > 0)
            .order_by(
                NewsCluster.run_date.desc(),
                NewsCluster.is_current.desc(),
                NewsCluster.importance.desc(),
                IssueDocent.created_at.desc(),
            )
            .limit(CANDIDATE_LIMIT)
        )
    ).all()

    deduplicated: list[tuple[Any, Any, Any]] = []
    seen: set[tuple[str, int]] = set()
    for docent, cluster, analysis in rows:
        stable_id = getattr(cluster, "stable_id", None)
        key = ("stable", int(stable_id)) if stable_id is not None else ("cluster", cluster.id)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append((docent, cluster, analysis))
    if not deduplicated:
        return []

    cluster_ids = [int(cluster.id) for _, cluster, _ in deduplicated]
    source_counts = {
        int(cluster_id): int(count)
        for cluster_id, count in (
            await db.execute(
                text(
                    "SELECT nc.id, count(DISTINCT n.news_source) "
                    "FROM news_cluster nc "
                    "JOIN news n ON n.id = ANY(nc.member_news_ids) "
                    "WHERE nc.id = ANY(:cluster_ids) "
                    "GROUP BY nc.id"
                ),
                {"cluster_ids": cluster_ids},
            )
        ).all()
    }
    all_sector_ids = sorted(
        {
            int(sector_id)
            for _, _, analysis in deduplicated
            for sector_id in (getattr(analysis, "sector_ids", None) or [])
        }
    )
    sector_name_by_id = {}
    if all_sector_ids:
        sector_name_by_id = {
            int(sector.id): str(sector.name_ko)
            for sector in (
                await db.execute(select(Sector).where(Sector.id.in_(all_sector_ids)))
            ).scalars()
        }

    return [
        LearningCandidate(
            docent,
            cluster,
            analysis,
            source_count=source_counts.get(int(cluster.id), 0),
            sector_names=tuple(
                sector_name_by_id.get(int(sector_id), str(sector_id))
                for sector_id in (getattr(analysis, "sector_ids", None) or [])
            ),
        )
        for docent, cluster, analysis in deduplicated
    ]


def candidate_to_scoring_row(candidate: LearningCandidate) -> dict:
    """운영 ORM 후보를 오프라인 v4 점수 모델 입력 형식으로 바꾼다."""
    hook_lines = getattr(candidate.docent, "hook_lines", None) or {}
    run_date = getattr(candidate.cluster, "run_date", None)
    return {
        "issue_id": candidate.issue_id,
        "cluster_id": int(candidate.cluster.id),
        "stable_id": getattr(candidate.cluster, "stable_id", None),
        "run_date": run_date.isoformat() if hasattr(run_date, "isoformat") else str(run_date),
        "importance": candidate.importance,
        "size": int(getattr(candidate.cluster, "size", 0) or 0),
        "source_count": candidate.source_count,
        "frame": str(getattr(candidate.analysis, "frame", "")),
        "scope": str(getattr(candidate.analysis, "scope", "")),
        "sector_ids": sorted(candidate.sector_ids),
        "sector_names": list(candidate.sector_names),
        "company_ids": sorted(candidate.company_ids),
        "title": str(candidate.docent.title),
        "hook": str(hook_lines.get("neutral", "")),
    }
