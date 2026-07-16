"""파이프라인 rolling-window·실패 전파 회귀 테스트."""

from datetime import date, datetime

import pytest

from app.db.queries import get_clusterable_news, get_unanalyzed_clusters
from services.embedder import score as score_module
from services.embedder.score import ClusterScore, persist_clusters
from services.pipeline.embedding_clusterer import EmbeddingClusterer


class _ScalarResult:
    def scalars(self):
        return self

    def all(self):
        return []


class _CaptureDB:
    def __init__(self):
        self.statements = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult()

    async def commit(self):
        self.commits += 1


async def test_clusterable_news_uses_full_window_not_analysis_flag():
    db = _CaptureDB()
    await get_clusterable_news(db, datetime(2026, 7, 1))
    where = str(db.statements[0].whereclause)
    assert "news.is_analyzed" not in where
    assert "news.embedding IS NOT NULL" in where


async def test_analysis_reads_only_current_cluster_snapshot():
    db = _CaptureDB()
    await get_unanalyzed_clusters(db, date(2026, 7, 16), 10)
    where = str(db.statements[0].whereclause)
    assert "news_cluster.is_current IS true" in where


async def test_persist_clusters_replaces_current_snapshot(monkeypatch):
    captured_records = []

    async def fake_upsert(_db, records):
        captured_records.extend(records)
        return len(records)

    monkeypatch.setattr(score_module, "upsert_news_clusters", fake_upsert)
    db = _CaptureDB()
    await persist_clusters(
        db,
        date(2026, 7, 16),
        [ClusterScore(member_news_ids=[10, 11], importance=0.8, stable_id=7)],
    )

    # UPSERT 전에 같은 날짜의 이전 스냅샷을 비활성화한다.
    assert "UPDATE news_cluster SET is_current" in str(db.statements[0])
    assert captured_records[0]["is_current"] is True


async def test_embedding_failure_is_propagated_for_airflow_retry(monkeypatch):
    clusterer = EmbeddingClusterer()

    async def fail_news():
        raise RuntimeError("embedding backend unavailable")

    async def succeed_chunks():
        return 3

    monkeypatch.setattr(clusterer, "_embed_news", fail_news)
    monkeypatch.setattr(clusterer, "_embed_chunks", succeed_chunks)
    errors: list[str] = []

    with pytest.raises(RuntimeError, match="임베딩 단계 실패"):
        await clusterer._embed_parallel(errors)
    assert errors == ["embed_news: embedding backend unavailable"]
