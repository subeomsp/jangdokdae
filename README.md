# jangdokdae

뉴스 수집부터 하루 세 가지 학습 화면까지 연결한 장독대 모노레포입니다.

```text
GitHub Actions
  → 뉴스 수집 → 임베딩 → 클러스터링 → LLM 분석·콘텐츠 생성
  → Neon PostgreSQL
  → FastAPI 오늘의 학습 API
  → Next.js 온보딩·읽기·퀴즈·완료 화면
```

## 디렉터리

- `jangdokdae-server`: 배치 파이프라인, FastAPI, DB 마이그레이션
- `jangdokdae-web`: 사용자용 Next.js MVP
- `.github/workflows/news-pipeline.yml`: 매일 09:07·15:37 KST 뉴스 파이프라인

## MVP 로컬 실행

서버를 먼저 실행합니다.

```bash
cd jangdokdae-server
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

새 터미널에서 프론트를 실행합니다.

```bash
cd jangdokdae-web
cp .env.example .env.local
npm ci
npm run dev
```

브라우저에서 <http://localhost:3000>을 열면 관심 섹터 선택부터 하루 세 가지 이슈와
퀴즈까지 이어집니다. 자세한 프론트 설정은 `jangdokdae-web/README.md`, 신규 운영 환경
구축은 `jangdokdae-server/docs/guide/02-github-actions-new-environment-setup.md`를 봅니다.
