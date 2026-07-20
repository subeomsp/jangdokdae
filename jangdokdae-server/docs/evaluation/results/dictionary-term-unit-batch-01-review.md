# 경제용어 분리 제안 1차 검수

## 요약

- 대상: 한국은행 복합 제목 8개
- DB 상태: `proposed`
- 모델: `gemini-2.5-flash`
- 프롬프트: 최초 6건 `bok-term-units-v1`, 별칭 보완 2건 `bok-term-units-v2`
- 코드 검사: 모든 용어와 별칭이 원문 제목 또는 정의에서 직접 확인됨
- 사람 승인: 대기

최초 제안에서 `경기조절정책`과 `바젤은행감독위원회`의 영문 별칭이 누락됐다.
프롬프트 v2와 결정적 영문 별칭 후처리를 추가하고 두 항목을 재제안했다. 변경 후 현재
골드셋 5개 × 3회 평가도 15/15 Trials, 평균 100점을 유지했다.

## 제안 내용

| 원문 제목 | 관계 | 화면용 용어와 별칭 | 검토 의견 |
| --- | --- | --- | --- |
| 간접금융/직접금융 | `distinct_concepts` | 간접금융(`Indirect Financing`), 직접금융(`Direct Financing`) | 승인 권장 |
| 경기조절정책/경제안정화정책 | `aliases` | 경기조절정책(`경제안정화정책`, `Business Adjustment Policy`, `Stabilization Policy`) | v2 재제안, 승인 권장 |
| 경제활동인구/비경제활동인구/경제활동참가율 | `distinct_concepts` | 경제활동인구, 비경제활동인구, 경제활동참가율 | 승인 권장 |
| 노동생산성/노동생산성지수 | `distinct_concepts` | 노동생산성, 노동생산성지수 | 개념과 지표가 별도이므로 승인 권장 |
| 리스크 온(Risk On)/오프(Off) | `distinct_concepts` | 리스크 온(`Risk On`), 리스크 오프(`Risk Off`) | 승인 권장 |
| 매입외환/환가료 | `distinct_concepts` | 매입외환, 환가료 | 자산과 수수료가 별도이므로 승인 권장 |
| 바젤은행감독위원회/바젤위원회(BCBS) | `aliases` | 바젤은행감독위원회(`바젤위원회`, `BCBS`, `Basel Committee on Banking Supervision`) | 결정적 별칭 보완, 승인 권장 |
| 원/위안 직거래시장 | `notation` | 원/위안 직거래시장 | `/`는 통화쌍 표기이므로 승인 권장 |

## 승인 후 동작

사람이 위 결과를 승인하면 `term_units_status=approved`와 검수 시각을 기록한다. 이
승인은 제목 분리 계획에만 적용된다. 화면용 쉬운 설명은 각 개별 용어마다 한국은행
원문을 근거로 별도로 생성하고 검증해야 한다.
