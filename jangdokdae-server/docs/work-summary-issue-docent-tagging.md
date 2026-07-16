# 작업 요약 — feat/issue-docent-tagging

> 역사 문서: `market_ids`·`sector_ids`·`company_ids`를 `issue_docent`에 직접 두던 설계는
> `f0a1b2c3d4e5` 마이그레이션에서 제거됐다. 현재 관심사 필터의 정본은 `news_analysis`이며,
> 아래 내용 중 해당 배열 컬럼과 백필 스크립트 설명은 더 이상 실행 가능한 운영 절차가 아니다.

> 브랜치 `feat/issue-docent-tagging` (base: `main`) · 커밋 6개 · 22 files, +816 / −50
> PR 본문으로도 사용 가능. (이 파일은 기록용 — 불필요하면 삭제 가능)

콘텐츠 파이프라인(issue_docent) 발행 품질·관심사 태깅을 보강한 묶음 작업. 설계 상세는 `docs/design/13~15` 참조.

## 무엇을 / 왜

| # | 작업 | 문제 → 해결 |
|---|------|------------|
| 1 | **issue_docent 시장·섹터·종목 태깅 + LLM 제목** | 발행 콘텐츠에 관심사(market/sector/company)가 없어 온보딩 기반 피드 필터 불가 + 제목이 원문 헤드라인 복사 → 컬럼·추출 추가, 제목은 LLM 생성 |
| 2 | **markets 택소노미 정합화** | 코드/마이그레이션(KR·OVERSEAS)과 운영 DB(거래소·지수 6종)가 불일치 → 온보딩 회사 필터가 빈 결과 → DB 6-market을 정본으로 코드·시드 정합화 |
| 3 | **발행 무가치 콘텐츠 품질 게이트** | 원문 무내용으로 모든 head가 honest-blank인 콘텐츠가 발행 가치 없이 저장(#159) → 생성 후/분석 전 두 게이트로 needs_review 격리 |
| 4 | **term_spans 본문 정합 필터** | 본문(content_heads)에 없는 용어가 term_spans에 저장(프런트 하이라이트 깨짐) → 본문 등장 용어만 보존 |

## 커밋

```
3b0b2ea feat(analyzer): issue_docent에 시장·섹터·종목 태깅 + LLM 제목 생성
926c13b fix(onboarding): markets 택소노미를 DB 정본(6-market)으로 정합화
cf4542b feat(analyzer): 발행 무가치 콘텐츠 품질 게이트(honest-blank·본문 부족)
285bd7b fix(analyzer): term_spans를 content_heads 본문에 등장하는 용어로 제한
ed9b14d docs(design): 콘텐츠 발행 품질 게이트·term_spans 설계 15
cc10751 chore(scripts): issue_docent 무가치·term_spans 백필 스크립트
```

## 주요 변경 파일

- **DB/모델**: `app/db/orm_models/issue_docent.py`(market/sector/company id 컬럼+GIN), `app/db/orm_models/market.py`(주석), `app/db/queries.py`(`resolve_market_ids`·`save_issue_docent` 확장·`search_companies` 정합·`MARKET_CODE_TO_EXCHANGES` 제거)
- **마이그레이션**: `f3a7c9d2e1b8`(issue_docent 컬럼 + 분기 head 2개 병합), `c2b5e8a4d017`(markets 6-market reseed)
- **분석/생성**: `services/analyzer/{schemas,content_generator,frames}.py`, `services/pipeline/news_analyzer.py`, `app/llm/{graph,state}.py`, `prompts/news_generate.yaml`, `app/config.py`(`max_blank_heads=2`,`min_source_body_chars=200`)
- **온보딩**: `app/api/routers/masters.py`
- **문서**: `docs/design/13·14·15`
- **스크립트**: `scripts/remediate_issue_docent.py`
- **테스트**: `tests/test_{queries,content_generator,news_analyzer,api_routers}.py` (전체 223 passed)

## 설계 결정 요약

- market 추출 = **종목 거래소**(`CompanyEntity.market` KOSPI/KOSDAQ) → `markets.code`, 종목 없는 해외 이슈는 `GLOBAL` 폴백.
- sector/company id는 `issue_docent`에 비정규화 저장(피드 조회 조인 회피, news_analyzer 분류 해소값 재사용).
- 제목은 호출 B(콘텐츠 생성)에서 LLM이 함께 출력, 누락 시 원문 제목 폴백.
- 무가치 판정 처리 = **needs_review 격리**(드롭 아님, `news_analysis.needs_review`).
- alembic 분기 head 2개(PR #13·#14) 병합으로 단일 head 복구.

## 운영 반영 기록

- **기존 데이터 리메디에이션 적용 완료**(프로덕션): `scripts/remediate_issue_docent.py --apply`
  - issue_docent **77행** term_spans phantom 용어 제거(행별 일부만, 정상 용어 유지)
  - honest-blank ≥2 **2행**(#159 cluster=310, #107 cluster=314)의 `news_analysis.needs_review=True`
  - 재스캔 검증: phantom 0건 · 미격리 blank 0건

## ⚠️ 미반영(운영 배포 시 필요)

운영 DB에 아래 마이그레이션이 **아직 미적용** — 적용 전에는 issue_docent 태깅 INSERT가 컬럼 부재로 실패한다.
```
alembic upgrade head   # f3a7c9d2e1b8(컬럼 추가) + c2b5e8a4d017(markets reseed)
```

## main 재동기화 (PR #15 이후)

작업 중 origin/main이 전진(PR #15)해 우리 `fix(onboarding)` 작업과 겹쳤다. 재동기화로 정리:
- **commit A(market 택소노미) 폐기** — main이 동일하게 처리함: 6-종 reseed(`bff69e760d43`), `MARKET_CODE_TO_EXCHANGES`를 KOSPI/KOSDAQ 키로 갱신, market.py에 description·tags 추가. 우리 reseed 마이그레이션(c2b5…)·설계 14 삭제.
- **마이그레이션 단일화** — main이 head를 `e89f78e7e898`로 이미 병합 → 우리 `f3a7c9d2e1b8`는 head 병합을 빼고 그 위에 issue_docent 컬럼만 추가하도록 재작성(단일 head).
- **테스트 로컬 전용 전환** — main이 `tests/`를 untrack + gitignore(`8bc4077`). 우리 테스트 변경도 추적 해제(디스크엔 유지, 로컬 검증).

## 검증

- 변경 영역 테스트(news_analyzer·content_generator·queries·frames) → 36 passed (전체 테스트는 로컬 전용)
- `uv run alembic heads` → 단일 head `f3a7c9d2e1b8`
- 참고: `tests/test_embedder.py`는 main의 embedder 변경 vs 구버전 로컬 테스트 불일치(추적 대상 아님·범위 밖)
