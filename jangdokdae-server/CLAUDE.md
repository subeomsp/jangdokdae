# 장독대 서버 작업 안내

저장소 루트의 [`../CLAUDE.md`](../CLAUDE.md)가 전체 프로젝트 인수인계와 현재 운영
정본이다. 서버에서 작업하기 전에 반드시 루트 문서를 먼저 읽는다.

현재 운영 배치는 Airflow가 아니라 `.github/workflows/news-pipeline.yml`의 GitHub
Actions가 담당한다. Airflow 코드는 향후 대안으로만 보존한다.

서버 검증은 다음 명령을 기본으로 한다.

```bash
uv sync --frozen --group pipeline --extra dev
uv run python -m pytest -q
uv run ruff check .
uv run alembic heads
uv run alembic current
```

로컬 `.env`와 운영 DB를 보호하고, 한국은행 공식 원문·사람 승인 분리안·사람 승인 설명·
평가 골드셋을 재생성 가능한 데이터처럼 삭제하거나 덮어쓰지 않는다.
