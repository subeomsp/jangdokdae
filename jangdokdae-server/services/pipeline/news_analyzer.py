"""NewsAnalyzer — 뉴스 분석 단계 조립 (fetch → classify → generate → persist).

설계 10 §9. EmbeddingClusterer가 적재한 상위 클러스터(news_cluster)를 importance 내림차순으로
받아, 이슈별로 LangGraph 에이전트(classify → generate)를 돌리고 결과를 news_analysis·issue_docent에
적재한다. 이슈 간 rate-limit, 부분 실패는 격리(한 클러스터 실패가 전체를 멈추지 않음)한다.

상류와 같은 DB-only 핸드오프: 대상은 `news_cluster` 중 news_analysis가 없는 것, 완료 시
멤버 News의 is_analyzed=True. LLM 호출(graph.invoke)은 동기라 to_thread로 오프로드한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.orm_models.news_cluster import NewsCluster
from app.db.queries import (
    get_cluster_articles,
    get_unanalyzed_clusters,
    mark_news_analyzed,
    resolve_company_ids,
    resolve_sector_ids,
    save_issue_docent,
    save_news_analysis,
)
from app.llm.graph import build_analysis_graph
from services.analyzer.article_fetcher import fetch_first_available
from services.analyzer.classifier import needs_review
from services.analyzer.schemas import (
    Article,
    ClassificationResult,
    ContentResult,
    Issue,
    QuizOutput,
)
from utils.dates import now_kst

logger = logging.getLogger(__name__)


class ClusterOutcome(NamedTuple):
    """한 클러스터 처리 결과 — 검수 큐 진입 여부 + 콘텐츠 skip 사유."""

    review: bool              # 검수 큐 진입(저신뢰·생성 가드·본문 부족)
    skipped_irrelevant: bool  # 비투자성으로 콘텐츠 생성·적재를 건너뜀(relevance 필터)
    low_source: bool          # 원문 본문 부족으로 생성을 건너뜀


class NewsAnalyzerState(TypedDict):
    """단계 실행 결과 요약 — Airflow XCom·러너 보고 형식(데이터가 아닌 카운트·실패 신호만)."""

    run_date: str           # 분석 실행 일자 (KST)
    clusters: int           # 분석 대상으로 집어온 클러스터 수
    analyzed: int           # 분류·적재까지 완료한 수(비투자성 skip 포함)
    needs_review: int       # 저신뢰로 검수 큐에 들어간 수
    skipped_irrelevant: int  # 비투자성으로 콘텐츠 생성을 건너뛴 수(relevance 필터)
    low_source: int         # 원문 본문 부족으로 콘텐츠 생성을 건너뛴 수
    errors: list[str]       # 클러스터별 실패 신호 — 부분 실패 가시성(빈 리스트=전부 성공)


class NewsAnalyzer:
    """상위 클러스터를 이슈별로 분류·생성·적재하는 분석 단계."""

    def __init__(self, graph=None, body_fetcher=fetch_first_available) -> None:
        self._graph = graph
        self._fetch_body = body_fetcher  # 주입 가능(테스트 시 외부 fetch 차단)

    @property
    def graph(self):  # noqa: ANN201
        if self._graph is None:
            self._graph = build_analysis_graph()
        return self._graph

    async def _build_issue(self, db: AsyncSession, cluster: NewsCluster) -> Issue:
        """대표 기사 본문 fetch + 서브 헤드라인으로 이슈를 구성한다."""
        articles = await get_cluster_articles(db, cluster.member_news_ids)
        if not articles:
            raise ValueError("클러스터 소속 기사를 찾지 못함")
        representative = articles[0]
        # 본문은 중심 근접순 후보를 순차 시도(페이월·실패 시 다음 후보 → 전부 실패 시 None).
        body = await self._fetch_body(a.url for a in articles)
        main = Article(title=representative.title, body=body or "", url=representative.url)
        subs = [Article(title=a.title, url=a.url) for a in articles[1:]]
        return Issue(cluster_id=cluster.id, main_article=main, sub_articles=subs)

    async def _persist(
        self,
        db: AsyncSession,
        cluster: NewsCluster,
        issue: Issue,
        classification: ClassificationResult,
        content: ContentResult | None,
        quizzes: QuizOutput | None,
        review: bool,
    ) -> None:
        # 태그(이름)를 마스터 id로 해소해 백필 — 관계형 조회·주가 연동의 조인 키.
        # 미매칭은 빠지고 원문 태그는 그대로 보존되므로, 마스터 미수록 기업·섹터에도 안전하다.
        company_ids = await resolve_company_ids(
            db, [t.name for t in classification.company_tags]
        )
        sector_ids = await resolve_sector_ids(db, classification.sector_tags)
        await save_news_analysis(
            db,
            cluster_id=cluster.id,
            scope=classification.scope,
            frame=classification.frame,
            origin=classification.origin,
            direction=classification.direction,
            confidence=classification.confidence,
            sector_tags=classification.sector_tags,
            company_tags=[t.model_dump() for t in classification.company_tags],
            company_ids=company_ids,
            sector_ids=sector_ids,
            term_tags=classification.term_tags,
            needs_review=review,
            is_investment_relevant=classification.is_investment_relevant,
        )
        # relevance 필터: 비투자성(content 없음)이면 분류만 남기고 콘텐츠 적재는 건너뛴다.
        if content is not None:
            await save_issue_docent(
                db,
                cluster_id=cluster.id,
                title=content.title or issue.main_article.title,
                hook_lines=content.hook_lines.model_dump() if content.hook_lines else {},
                content_heads=[h.model_dump() for h in content.heads],
                connection_module=[c.model_dump() for c in content.connection_module],
                evidence_spans=[e.model_dump() for e in content.evidence_spans],
                term_spans=[t.model_dump() for t in content.term_spans],
                quizzes=[q.model_dump() for q in quizzes.quizzes] if quizzes else [],
            )
        await mark_news_analyzed(db, cluster.member_news_ids)

    async def analyze_cluster(self, db: AsyncSession, cluster: NewsCluster) -> ClusterOutcome:
        """클러스터 1건을 분류·생성·적재하고 commit한다. 처리 결과(검수·skip)를 반환.

        한 이슈의 happy-path(본문 fetch → classify/generate → 적재 → commit)를 모은 단위 —
        run()의 루프와 분석 전용 러너(scripts.run_analysis)가 함께 재사용한다. 실패 격리·
        이슈 간 간격은 호출부 책임이다(여기선 예외를 잡지 않는다).

        relevance 필터: 분류가 비투자성(is_investment_relevant=false)이면 그래프가 generate를
        건너뛰어 content가 없다 → 분류만 적재하고 콘텐츠는 생략(skipped_irrelevant).
        """
        issue = await self._build_issue(db, cluster)
        # 그래프 노드(classify·generate)가 내부에서 to_thread로 LLM 호출을 오프로드하므로
        # 여기선 ainvoke로 직접 await한다. enrich 노드의 key 조회용으로 db를 함께 넘긴다.
        result = await self.graph.ainvoke({"issue": issue, "db": db})
        classification: ClassificationResult = result["classification"]
        content: ContentResult | None = result.get("content")
        quizzes: QuizOutput | None = result.get("quizzes")
        skipped_irrelevant = content is None and not classification.is_investment_relevant
        low_source = content is None and classification.is_investment_relevant
        if skipped_irrelevant:
            logger.info("relevance 필터: 비투자성 — 콘텐츠 생성 생략 cluster_id=%s", cluster.id)
        elif low_source:
            logger.info("본문 부족 — 콘텐츠 생성 생략, needs_review cluster_id=%s", cluster.id)
        review = (
            needs_review(classification)
            or result.get("generation_review", False)
            or low_source
        )
        await self._persist(db, cluster, issue, classification, content, quizzes, review)
        await db.commit()
        return ClusterOutcome(
            review=review,
            skipped_irrelevant=skipped_irrelevant,
            low_source=low_source,
        )

    async def run(self, db: AsyncSession) -> NewsAnalyzerState:
        run_date = now_kst().date()
        clusters = await get_unanalyzed_clusters(
            db, run_date, settings.analysis_top_cluster_count
        )
        analyzed = 0
        review_count = 0
        skipped_count = 0
        low_source_count = 0
        errors: list[str] = []

        for cluster in clusters:
            try:
                outcome = await self.analyze_cluster(db, cluster)
                analyzed += 1
                review_count += int(outcome.review)
                skipped_count += int(outcome.skipped_irrelevant)
                low_source_count += int(outcome.low_source)
            except Exception as exc:  # noqa: BLE001 — 한 클러스터 실패가 전체를 멈추지 않게 격리
                await db.rollback()
                logger.exception("클러스터 분석 실패 cluster_id=%s", cluster.id)
                errors.append(f"cluster={cluster.id}: {exc}")
            # 이슈 간 호출 간격(rate limit 완화).
            if settings.llm_request_delay_seconds > 0:
                await asyncio.sleep(settings.llm_request_delay_seconds)

        logger.info(
            "NewsAnalyzer 완료 run_date=%s clusters=%d analyzed=%d needs_review=%d "
            "skipped_irrelevant=%d low_source=%d errors=%d",
            run_date, len(clusters), analyzed, review_count, skipped_count,
            low_source_count, len(errors),
        )
        if errors:
            # 성공한 클러스터는 이미 commit되어 재시도에서 자동 제외된다. 실패를 호출자에게
            # 올려야 Airflow가 Task를 재시도하고 전체 실패를 성공으로 오인하지 않는다.
            raise RuntimeError("뉴스 분석 단계 일부 실패: " + "; ".join(errors))
        return NewsAnalyzerState(
            run_date=str(run_date),
            clusters=len(clusters),
            analyzed=analyzed,
            needs_review=review_count,
            skipped_irrelevant=skipped_count,
            low_source=low_source_count,
            errors=errors,
        )
