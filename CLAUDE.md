# 장독대 프로젝트 인수인계

> 상태 기준일: 2026-07-21
>
> 개발 담당 AI: Claude Code
>
> 범위: 제품 방향, 구현·운영 현황, 데이터 보존 규칙, 검증 방법, 후속 작업

## 0. 가장 먼저 알아야 할 것

이 문서는 저장소 루트에서 작업하는 Claude Code의 현재 정본이다. 하위 디렉터리의 과거
설계 문서에는 Airflow가 운영 정본이라고 쓰인 부분과 오래된 Alembic revision 예시가
남아 있으므로, 현황이 충돌하면 이 문서와 실제 코드를 우선 확인한다.

이번 인수인계는 **개발을 담당하는 AI를 Codex에서 Claude Code로 바꾸는 것**이다. 서비스가
운영 중에 호출하는 LLM은 계속 Google Cloud Vertex AI의 Gemini다. 사용자가 별도로 요청하지
않는 한 Anthropic API로 런타임 모델을 교체하지 않는다. 런타임 모델 교체는 인증, 비용,
구조화 출력, 프롬프트, 회귀 평가를 함께 다시 검토해야 하는 별도 작업이다.

비밀값은 로컬 `jangdokdae-server/.env`, GitHub Actions Secrets/Variables, 배포 서비스의
환경변수에만 존재해야 한다. DB URL, API 키, OAuth secret, 서비스 계정 키를 문서·커밋·이슈에
기록하지 않는다.

사용자와는 한국어로 대화한다. 모든 응답은 반드시 다음 형식으로 시작한다.

```text
━━━━━━━━━━━━━━━━━━━━

🤖 Assistant

━━━━━━━━━━━━━━━━━━━━
```

## 1. 서비스가 해결하려는 문제

장독대는 뉴스를 더 많이 보여주는 피드가 아니다. 주식 초보자가 하루에 꼭 알아야 할 세 가지
이슈만 이해하고 퀴즈까지 풀면 학습을 끝낼 수 있게 하는 서비스다.

핵심 사용자 가치는 다음과 같다.

1. 뉴스 과잉을 줄인다.
2. 어려운 경제·투자 뉴스를 초보자 언어로 풀어준다.
3. 사용자가 매수·매도 답을 받는 대신 시장을 스스로 읽을 수 있게 돕는다.
4. 하루 학습량에 명확한 끝을 만든다.

현재 확정된 MVP 규칙은 다음과 같다.

- 하루 최대 3개 이슈를 제공한다. 5개로 늘리지 않는다.
- 역할은 `내 관심(focus) → 시장 맥락(context) → 시야 넓히기(discovery)`다.
- 양질의 후보가 3개보다 적으면 실제 수만 보여준다. AI가 근거 없는 빈자리 콘텐츠를 만들지 않는다.
- 각 이슈를 읽은 뒤 퀴즈 한 문제를 제출해야 완료된다.
- 정답 여부와 무관하게 한 번 제출하면 해당 이슈 학습은 완료된다.
- 세 이슈를 모두 마치면 오늘의 학습이 끝난다.
- 오늘의 학습이 메인이고, 과거 콘텐츠 탐색은 완료 후 보조 기능으로 둔다.
- 한국은행 용어사전은 네 번째 학습 콘텐츠가 아니다. 본문의 어려운 용어에 밑줄을 표시하고
  hover/tap으로 짧은 설명을 보여주는 보조 레이어다.

## 2. 저장소와 현재 아키텍처

```text
GitHub Actions (09:07, 15:37 KST 또는 수동 실행)
  → 뉴스·공시 수집
  → 전처리
  → 임베딩
  → HDBSCAN 클러스터링·주요 이슈 선정
  → Vertex AI Gemini 분류·해설·퀴즈 생성
  → Neon PostgreSQL + pgvector
  → FastAPI 오늘의 학습·이슈·사전 API
  → Next.js MVP
```

주요 디렉터리:

- `jangdokdae-server`: FastAPI, 배치 파이프라인, Alembic, 평가 하니스
- `jangdokdae-web`: Next.js 16 사용자 MVP
- `.github/workflows/news-pipeline.yml`: 정기 뉴스 파이프라인
- `jangdokdae-server/evaluation/dictionary`: 한국은행 용어 분리·설명 회귀 평가
- `jangdokdae-server/docs`: 설계, 운영 가이드, 평가 결과

### 운영 오케스트레이션

개인 노트북을 24시간 켜둘 수 없어서 운영 정본을 Airflow에서 GitHub Actions로 전환했다.
Airflow DAG와 Docker Compose는 삭제하지 않았지만 현재 주 실행기는 아니다.

워크플로는 다음 두 시각에 실행된다.

- `7 0 * * *`: 매일 09:07 KST
- `37 6 * * *`: 매일 15:37 KST

`workflow_dispatch`로 `premarket`, `morning`, `afternoon`, `afterhours` 세션을 수동 실행할
수 있다. 동일 파이프라인의 중복 실행은 허용하지 않고 대기시키며, 제한 시간은 90분이다.

Google Cloud 인증은 서비스 계정 JSON을 GitHub에 저장하지 않고 Workload Identity
Federation을 사용한다. 사용자는 2026-07-20 GitHub Actions 실행과 Neon 적재가 정상임을
확인했다. GCP Cloud Shell에서 `Regional Access Boundary ... Gaia id not found` 경고가
반복됐지만 API 활성화 작업 자체는 성공했고, 이후 WIF 인증도 성공했다.

필수 GitHub 설정 이름은 워크플로 파일을 정본으로 삼는다.

- Secrets: `DATABASE_URL`, `SECRET_KEY`, `OPENDART_API_KEY`
- 선택 Secrets: `ECOS_API_KEY`, `KRX_ID`, `KRX_PW`
- Variables: `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`,
  `GOOGLE_CLOUD_LOCATION`, `VERTEX_MODEL`, `EMBED_MODEL`

### API와 프론트

FastAPI에는 인증, 관심사, 온보딩, 이슈, 오늘의 학습, 용어사전 API가 구현돼 있다.
오늘의 학습 API는 최근 7일 후보에서 stable cluster를 중복 제거하고 최대 세 개를 선택한다.

Next.js MVP에는 다음 화면과 흐름이 있다.

- 관심 섹터 온보딩
- 하루 세 이슈 홈
- 이슈 읽기와 인라인 용어 설명
- 이슈별 퀴즈
- `3/3` 완료 화면

게스트 사용자의 관심사, 당일 계획, 진행 상태는 `localStorage`에 저장한다. 로그인 사용자는
퀴즈 완료를 DB에도 기록할 수 있다.

**현재 프론트는 기능 MVP이지 디자인 승인본이 아니다.** 사용자는 기존 AI 템플릿 같은
디자인을 선호하지 않았다. 다음 디자인은 듀오링고·말해보카처럼 일일 학습 진행이 명확하되,
캐릭터를 복제하지 않고 심플하고 트렌디해야 한다. 기능 흐름과 API 계약은 재사용하되 시각
디자인은 새로 검토한다.

GitHub Actions 배치는 운영 중이지만 공개 API·프론트의 실제 배포 URL과 현재 생존 여부는
저장소에 기록돼 있지 않다. 공개 배포가 필요하면 사용자에게 현재 호스팅 위치를 확인하고,
확인 전에는 배포 완료라고 단정하지 않는다.

## 3. 지금까지 완료한 주요 작업

### 뉴스 파이프라인과 데이터

- RSS 뉴스와 OpenDART 공시 수집
- 본문 전처리와 중복 제거
- `jhgan/ko-sroberta-multitask` 768차원 임베딩
- 제목·본문 가중 결합과 HDBSCAN 클러스터링
- 클러스터 중요도 산정과 주요 이슈 선택
- Vertex AI 기반 투자 관련성·프레임 분류
- 초보자용 해설, 근거 span, 용어 span, 퀴즈 생성
- 원문 부족과 회피성 답변이 많은 콘텐츠를 `needs_review`로 격리하는 품질 게이트
- GitHub Actions 하루 2회 실행과 수동 실행
- 새 Neon DB 마이그레이션 및 파이프라인 적재

### 하루 세 가지 학습 MVP

- `GET /api/v1/learning/today`
- `POST /api/v1/learning/today/{issue_id}/quiz`
- 관심 → 시장 맥락 → 시야 확장의 최대 세 자리 선택
- stable cluster 중복 제거
- 게스트/로그인 사용자 완료 흐름
- Next.js 온보딩·홈·읽기·퀴즈·완료 화면
- Playwright MVP 흐름 테스트

### 한국은행 원문 기반 인라인 용어사전

- 한국은행 「경제금융용어 800선」 PDF에서 공식 원문 789개 추출·저장
- 원문과 AI 화면용 설명을 별도 테이블로 분리
- 책 페이지와 PDF 실제 페이지, 원문 URL, 해시 보존
- 현재 콘텐츠에서 필요한 한국은행 항목 선별
- 복합 제목을 다음 네 관계로 분류하는 작업 흐름 구현
  - `single`
  - `distinct_concepts`
  - `aliases`
  - `notation`
- AI 분리 제안은 `proposed`, 사람 검수 후에만 `approved`
- 승인된 개별 용어만 한국은행 원문 기반 쉬운 설명 후보 생성
- 생성과 별도 검증을 분리하고 90점 이상만 승인 후보로 인정
- 1차 검증 실패 시 실패 사유를 넣어 최대 한 번 자동 보정하는 `bok-definition-v5`
  (v5에서 검증기가 "함께 정의되는 개념 누락=fail"과 "용어의 하류 파급효과 생략=ok"을 구분)
- 사람 승인 전에는 최종 결과도 `candidate` 유지
- 본문 첫 등장에만 밑줄을 표시하고 tooltip/sheet와 원문 링크 제공

### 평가 체계

에이전트 평가는 마지막 출력만 보는 대신 Task, transcript, outcome, metrics를 분리했다.

- 용어 분리 골드셋: 13개 승인 Task
- 쉬운 설명 골드셋: 34개 승인 Task (1차 5 · 2차 5 · 3차 24, `definition_batch_0N` 태그로 구분)
- 각 중요 Task를 3회 반복해 `pass@1`과 `pass^3` 측정
- 코드 검사와 별도 LLM 원문 근거 검증 결합
- 프롬프트 버전, 모델, 원문 해시, 전체 시도 JSON 보존

2차 배치까지의 마지막 PASS 평가(v5, 2026-07-21):

- 10 Task × 3회 = 30 Trials, 30/30 통과, `pass@1 = pass^3 = 100%`
- 2차 첫 평가에서 `노동생산성지수`가 문장수 게이트(≤3문장) ↔ 완전성 검증기 충돌로
  3/3 실패 → 검증기가 근거성을 완전성과 혼동하지 않도록 v5로 고친 뒤 통과.

3차 배치(24개) 상태 — 데이터는 승인 완료·골드셋 반영, **평가 게이트는 HOLD**:

- 승인 설명은 사람 검수를 통과한 정본이고 골드셋에 들어갔다(34 Task).
- 34 Task 반복 평가에서 `M&A`·`유동성`이 노동생산성지수와 같은 구조로 실패했다.
  원문이 하위 항목을 열거하는데(M&A의 4가지 방법, 유동성의 파생 개념) 검증기가 이를
  모두 요구해 3문장 게이트와 충돌한다. v5는 "하류 파급효과 생략 OK"까지만 다뤘고,
  "열거된 구성 항목은 나열이면 충분"은 미반영이다. → 검증기 v6 보정 + 재평가가 후속(P0).
- Gemini 429 rate limit으로 34×3=102 Trial 대규모 재평가가 현재 지연된다. 청크 분할
  실행이 필요하다.

이 결과는 **작은 회귀 게이트**일 뿐 전체 789개 자동 승인을 허용하는 근거가 아니다.

## 4. 2026-07-22 DB 스냅샷

아래 수치는 현재 로컬 `.env`가 가리키는 새 Neon DB를 읽기 전용으로 확인한 값이다. 데이터
파이프라인 실행에 따라 변할 수 있다.

| 항목 | 현재 값 |
| --- | ---: |
| 뉴스 | 1,182 |
| 뉴스 분석 | 83 |
| 생성 이슈 콘텐츠 | 79 |
| 한국은행 원문 항목 | 789 |
| 현재 콘텐츠 기반 선택 원문 | 25 |
| `term_units_status=approved` 원문 | 33 |
| `term_units_status=pending` 원문 | 756 |
| 한국은행 기반 `approved + verified` 설명 | 35 |
| 기존 LLM 레거시 용어 | 340 |

Alembic 현재 head는 `e0a2b4c6d8f0` 하나다.

기존 LLM 용어 340개는 사람이 검증한 데이터가 아니다. 삭제할 필요는 없지만 앞으로의
정답이나 자동화 품질 근거로 사용하지 않는다. 한국은행 원문과 `approved + verified` 설명을
정본으로 사용한다.

뉴스, 임베딩, 클러스터, 분석, 콘텐츠는 파이프라인으로 재생성할 수 있다. 반면 다음 데이터는
사람의 판단 또는 공식 출처를 포함하므로 마이그레이션·초기화 때 반드시 보존한다.

- `dictionary_source_entries`의 한국은행 원문·페이지·해시
- 승인된 `term_units`와 검수 상태
- `dictionary_terms`의 한국은행 기반 승인 설명
- `evaluation/dictionary/tasks/*.jsonl` 골드셋

## 5. 용어사전 작업을 이어가는 정확한 순서

용어사전은 **분리 승인 → 개별 설명 생성 → 사람 검수 → 설명 승인 → 골드셋 추가 → 반복 평가**
순서를 지킨다. 원문 전체를 먼저 짧게 요약하고 나중에 억지로 나누지 않는다.

다음 작업 대상으로 합의한 5개 용어는 다음과 같다.

1. 경제활동참가율
2. 노동생산성
3. 노동생산성지수
4. 리스크 온
5. 리스크 오프

서버 디렉터리에서 실행한다.

```bash
cd jangdokdae-server

uv run python -m scripts.generate_dictionary_term_candidates \
  --term 경제활동참가율 \
  --term 노동생산성 \
  --term 노동생산성지수 \
  --term '리스크 온' \
  --term '리스크 오프'
```

생성 결과가 90점 이상이어도 자동 승인하지 않는다. 한국은행 원문과 후보 문장을 사람이
직접 비교하고, 합쳐진 개념, 과도한 일반화, 잘못된 조사, 원문 밖 예시를 확인한다. 문제가
있으면 한 용어씩 `--review-feedback`으로 다시 생성한다.

검수 완료 후에만 승인한다.

```bash
uv run python -m scripts.review_dictionary_term_candidates \
  --term 경제활동참가율 \
  --term 노동생산성 \
  --term 노동생산성지수 \
  --term '리스크 온' \
  --term '리스크 오프'
```

승인된 설명을 골드셋에 추가하고 반복 평가한다.

```bash
uv run python -m scripts.export_dictionary_definition_gold \
  --term 경제활동참가율 \
  --term 노동생산성 \
  --term 노동생산성지수 \
  --term '리스크 온' \
  --term '리스크 오프'

uv run python -m evaluation.dictionary.run_definition --repeats 3
```

새 실패 사례가 나오면 점수만 올리거나 프롬프트에 예외를 무작정 추가하지 않는다. 사람 판정이
맞는지 확인하고, 일반화할 수 있는 코드 규칙·프롬프트 규칙·골드 회귀 사례로 나눠 반영한다.

## 6. 앞으로 필요한 작업

### P0 — 바로 이어서 할 일

1. **검증기 v6 보정 + 3차 배치 재평가** (가장 먼저)
   - 3차 배치(24개, `definition_batch_03`)는 승인·골드셋까지 끝났으나 **평가 게이트가 HOLD**다.
   - `M&A`·`유동성`이 노동생산성지수와 같은 구조로 실패한다. 검증기가 "열거된 하위 항목은
     간결히 나열하면 충분하고, 각각을 상세 정의할 필요는 없다"를 구분하도록 v6로 보정한다.
     이는 v5의 "하류 파급효과 생략 OK" 원칙의 연장이다(사용자가 택한 브레비티 방향).
   - `경제활동참가율`의 1회 `unsupported_number` 슬립도 재현/원인 확인한다.
   - v6 후 34 Task × 3 재평가로 `pass^3` 회복을 확인하고 결과를 커밋한다. Gemini 429로
     102 Trial 일괄 실행이 막히면 골드셋을 청크로 나눠 돌리고 지표를 합산한다.

2. **쉬운 설명 4차 배치** (v6 게이트 안정화 후)
   - 다음 대상은 미정. §5 순서(분리 승인→생성→검수→승인→골드셋→평가)를 반복한다.
   - 선별된 pending 원문에서 초보자 가치가 높은 용어를 고른다. 분리 단위가 `approved`인지
     먼저 확인하고, 없으면 분리 승인부터 한다.
   - 생성 결과가 90점이어도 자동 승인하지 않는다. 실패 transcript를 읽고 회귀 조건을 추가한다.

2. **하루 세 콘텐츠의 선택 기준 고도화**
   - 현재 코드는 최신 실행일과 클러스터 중요도 순서를 유지하며 세 역할을 채운다.
   - 주린이에게 정말 필요한 세 개라는 근거를 평가할 별도 골드셋이 없다.
   - 시장 영향도, 설명 가능성, 중복도, 섹터 다양성, 초보자 학습 가치의 명시적 점수와
     사람 평가 데이터를 만든다.
   - 후보가 부족할 때는 계속 적은 수만 반환하고 근거 없는 AI 콘텐츠를 만들지 않는다.

3. **프론트 시각 디자인 재설계**
   - 현재 API와 학습 상태 로직은 유지 가능하다.
   - 사용자가 승인하지 않은 기존 외형을 기준으로 미세 조정하지 말고 시각 시스템부터 다시 잡는다.
   - 모바일 우선, 하루 진행도, 한 화면 한 행동, 짧은 문장, 과도한 카드·그라데이션 금지.
   - 최소한 온보딩, 오늘 홈, 읽기, 퀴즈 피드백, 완료 화면을 하나의 일관된 시스템으로 만든다.

4. **실제 공개 배포 상태 확인**
   - GitHub Actions 배치는 정상 확인됐다.
   - API와 프론트의 현재 호스팅 서비스·URL은 사용자에게 확인한다.
   - 운영 API라면 CORS, `FRONTEND_BASE_URL`, HTTPS 쿠키, OAuth callback을 다시 검증한다.

### P1 — MVP 완성도를 높이는 일

- 용어 분리 골드셋을 13개에서 최소 24개로 확장한다.
- 쉬운 설명 골드셋을 대표 유형 20~30개까지 확장한다.
- 아직 미구현인 용어 분리 정확성 LLM 루브릭을 추가한다.
- 실제 뉴스 본문 인라인 매칭 골드셋을 만들고 false positive/negative를 측정한다.
- 오늘 학습 완료 후 기존 콘텐츠를 볼 수 있는 보조 라이브러리를 기획·구현한다.
- 사용자 관심 섹터가 정말 필요한지 게스트 기본 큐레이션과 비교 실험한다.
- 로그인 사용자의 당일 계획을 서버에 고정해 여러 기기에서도 같은 세 이슈를 보게 한다.
- 관리자 검수 화면을 만들어 용어 분리안·설명 후보·`needs_review` 콘텐츠를 한곳에서 본다.
- 파이프라인 실행 시간, LLM 호출 수·비용, 수집 실패, 후보 부족을 관측 가능하게 만든다.

### P2 — 운영과 기술 부채

- `langchain_google_vertexai.ChatVertexAI`는 LangChain 3.2에서 deprecated다.
  LangChain 4 전에 `langchain_google_genai.ChatGoogleGenerativeAI` 전환을 검토하되, 구조화
  출력과 전체 평가를 다시 실행한다.
- `IssueDocent.is_published`는 현재 모든 운영 행이 `false`지만 오늘의 학습 API는 이 필드를
  필터링하지 않는다. 필드의 의미를 확정하고 API·생성 파이프라인을 일치시킨다.
- `services.pipeline.runner` docstring과 일부 과거 문서는 Airflow를 운영 정본으로 설명한다.
  실제 운영 정본인 GitHub Actions에 맞게 차례로 정리한다.
- `docs/guide/02-github-actions-new-environment-setup.md`의 Alembic 정상 출력 예시는 과거
  revision이다. 고정 hash를 쓰지 않거나 현재 head로 갱신한다.
- `.env.example`에 `GOOGLE_API_KEY`, `DICTIONARY_MODEL`, `DICTIONARY_FALLBACK_MODEL`,
  `DICTIONARY_GROUNDED_MODEL`, 분석·품질 게이트 override가 충분히 설명돼 있지 않다.
- API의 발행 가능 조건과 `needs_review`, `is_published`, 퀴즈 존재 조건을 하나의 정책으로
  문서화하고 테스트한다.
- 과거 콘텐츠의 사전 매칭을 재계산하는 안전한 backfill과 dry-run 도구를 준비한다.

## 7. 개발·검증 명령

### 서버

```bash
cd jangdokdae-server
uv sync --frozen --extra dev
uv run alembic heads
uv run alembic current
uv run python -m pytest -q
uv run ruff check .
```

`uv run pytest`가 시스템의 다른 pytest를 선택한 사례가 있었으므로 테스트는
`uv run python -m pytest`를 사용한다.

2026-07-20 마지막 전체 검증은 `297 passed, 1 warning`이었다. warning은 Starlette
TestClient의 httpx 사용 deprecation이며 테스트 실패는 아니다.

DB 모델을 변경하면 ORM과 쿼리를 함께 수정하고 Alembic migration을 만든다.

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic check
```

마이그레이션 전에는 `.env`가 어느 DB를 가리키는지 확인한다. 운영 DB에서 파괴적 SQL,
전체 삭제, 무제한 backfill을 실행하지 않는다.

### 프론트

```bash
cd jangdokdae-web
npm ci
npm run lint
npm run typecheck
npm run build
```

E2E는 실제 FastAPI와 DB가 필요하다.

```bash
npm run test:e2e
```

### 파이프라인

로컬 1회 실행은 DB를 변경하고 Vertex AI 비용을 발생시킨다. 사용자가 실행을 요청했거나
대상 DB와 세션을 명확히 확인한 경우에만 실행한다.

```bash
cd jangdokdae-server
uv run python -m services.pipeline.runner morning
```

운영 수동 실행은 GitHub Actions의 `Jangdokdae News Pipeline`에서 세션을 선택한다.

## 8. 작업 원칙

- 개인 프로젝트이므로 별도 브랜치는 필수가 아니며 `main`에 작은 논리 단위로 커밋해도 된다.
- 사용자는 큰 덩어리 한 커밋보다 검토 가능한 작은 커밋을 선호한다.
- 기존 변경이 있으면 사용자의 작업으로 보고 덮어쓰거나 되돌리지 않는다.
- 기능 변경은 관련 테스트와 실제 위험에 비례한 검증까지 수행한다.
- 생성형 AI 결과를 DB에 넣었다는 이유만으로 성공 처리하지 않는다. 원문 근거, 코드 게이트,
  반복 평가, 사람 검수를 구분한다.
- 공식 원문과 사람 승인 데이터는 보존하고, 재생성 가능한 파이프라인 데이터와 구분한다.
- 자동 제안과 자동 승인을 분리한다. 현재 사전 자동 승인은 허용되지 않는다.
- 뉴스 콘텐츠와 사전 설명에 매수·매도 권유, 수익 보장, 원문 밖 수치·전망을 추가하지 않는다.
- 사용자가 요청하지 않은 운영 배포, 외부 메시지, 유료 대량 호출을 임의로 실행하지 않는다.

## 9. 새 세션에서 첫 확인 순서

1. 루트에서 `git status --branch --short`로 작업 트리가 깨끗한지 확인한다.
2. `git log --oneline -10`으로 이 문서 이후 변경을 확인한다.
3. 서버 `uv run alembic heads`와 `current`가 같은지 확인한다.
4. 전체 테스트를 돌리기 전 관련 소형 테스트부터 실행한다.
5. DB 작업이면 먼저 read-only count와 대상 행 상태를 확인한다.
6. 다음 용어 5개 작업을 시작한다면 분리 단위가 이미 `approved`인지 먼저 확인한다.
7. 프론트 작업이면 기능 흐름은 보존하되 기존 디자인이 승인본이 아님을 기억한다.

## 10. 반드시 읽을 문서

- `README.md`: 현재 모노레포 실행 개요
- `.github/workflows/news-pipeline.yml`: 운영 배치의 실제 정본
- `jangdokdae-server/docs/design/16-daily-learning-mvp.md`: 하루 세 가지 학습 규칙
- `jangdokdae-server/docs/guide/02-github-actions-new-environment-setup.md`: 신규 운영 환경 구축
- `jangdokdae-server/docs/guide/03-bok-inline-glossary.md`: 한국은행 사전 운영 순서
- `jangdokdae-server/docs/evaluation/10-dictionary-agent-eval-plan.md`: 사전 평가와 자동화 기준
- `jangdokdae-server/docs/evaluation/results/dictionary-definition-eval-2026-07-21-153655.md`:
  현재 쉬운 설명 v5 평가 결과(2차 배치 반영, 30/30 통과)
- `jangdokdae-server/evaluation/dictionary/tasks/README.md`: 골드셋 규칙
- `jangdokdae-web/README.md`: 프론트 기능과 로컬 실행

마지막 기능 기준 커밋은 다음 두 개다.

- `4e26739 feat(dictionary): add third grounded definition batch to goldset` (평가 게이트 HOLD)
- `a3f8bb6 fix(dictionary): separate grounding from completeness in definition gate` (마지막 PASS)
