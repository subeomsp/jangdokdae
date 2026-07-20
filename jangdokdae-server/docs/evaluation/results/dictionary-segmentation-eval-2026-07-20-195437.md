# 한국은행 용어 분리 에이전트 평가 결과

## 요약

- 모델: `gemini-2.5-flash`
- 프롬프트 버전: `bok-term-units-v1`
- 실행 시각(UTC): `2026-07-20T10:53:47.265681+00:00`
- Task: 5개 × 3회 = 15 Trials
- `pass@1`: 100.0%
- `pass^3`: 100.0%
- 전체 Trial 통과: 15/15
- 평균 점수: 100.00
- 즉시 실패: 0건
- 실행 오류: 0건

## 관계별 결과

| 관계 | Task | Trial 통과율 | pass@1 | pass^3 | 평균 점수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `distinct_concepts` | 2 | 100.0% | 100.0% | 100.0% | 100.00 |
| `aliases` | 1 | 100.0% | 100.0% | 100.0% | 100.00 |
| `notation` | 1 | 100.0% | 100.0% | 100.0% | 100.00 |
| `single` | 1 | 100.0% | 100.0% | 100.0% | 100.00 |

## Trial 상세

| Task | 원문 제목 | Trial | 기대/예측 관계 | 점수 | 통과 | 지연 | 실패 원인 |
| --- | --- | ---: | --- | ---: | --- | ---: | --- |
| `bok-seg-001` | 단리/복리 | 1 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 5338ms | - |
| `bok-seg-001` | 단리/복리 | 2 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 5324ms | - |
| `bok-seg-001` | 단리/복리 | 3 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 3734ms | - |
| `bok-seg-002` | 명목금리/실질금리 | 1 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 6302ms | - |
| `bok-seg-002` | 명목금리/실질금리 | 2 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 6085ms | - |
| `bok-seg-002` | 명목금리/실질금리 | 3 | `distinct_concepts` / `distinct_concepts` | 100.00 | PASS | 4485ms | - |
| `bok-seg-003` | 환매조건부매매/RP/Repo | 1 | `aliases` / `aliases` | 100.00 | PASS | 7154ms | - |
| `bok-seg-003` | 환매조건부매매/RP/Repo | 2 | `aliases` / `aliases` | 100.00 | PASS | 6307ms | - |
| `bok-seg-003` | 환매조건부매매/RP/Repo | 3 | `aliases` / `aliases` | 100.00 | PASS | 5774ms | - |
| `bok-seg-004` | 산업연관표(I/O Tables) | 1 | `notation` / `notation` | 100.00 | PASS | 1ms | - |
| `bok-seg-004` | 산업연관표(I/O Tables) | 2 | `notation` / `notation` | 100.00 | PASS | 0ms | - |
| `bok-seg-004` | 산업연관표(I/O Tables) | 3 | `notation` / `notation` | 100.00 | PASS | 0ms | - |
| `bok-seg-005` | 빅테크 | 1 | `single` / `single` | 100.00 | PASS | 0ms | - |
| `bok-seg-005` | 빅테크 | 2 | `single` / `single` | 100.00 | PASS | 0ms | - |
| `bok-seg-005` | 빅테크 | 3 | `single` / `single` | 100.00 | PASS | 0ms | - |

## 현재 게이트 판정

**PASS** — 소형 회귀 게이트를 통과했습니다. 자동 승인 전에는 골드셋을 24개까지 확장해야 합니다.
