# 한국은행 개별 용어 쉬운 설명 평가 결과

## 요약

- 모델: `gemini-2.5-flash`
- 프롬프트 버전: `bok-definition-v3`
- 실행 시각(UTC): `2026-07-20T12:11:19.836831+00:00`
- 통과 점수: 90점
- Task: 5개 × 3회 = 15 Trials
- `pass@1`: 60.0%
- `pass^3`: 40.0%
- 전체 Trial 통과: 12/15
- 평균 점수: 88.20
- 코드 검사 실패: 1건
- 원문 근거 미지원: 1건
- 실행 오류: 1건

## Trial 상세

| Task | 용어 | Trial | 점수 | 근거 | 통과 | 지연 | 실패 원인 |
| --- | --- | ---: | ---: | --- | --- | ---: | --- |
| `bok-def-001` | 간접금융 | 1 | 95 | supported | FAIL | 19970ms | forbidden_phrase:대중에게 예금을 받아 |
| `bok-def-001` | 간접금융 | 2 | 95 | supported | PASS | 17207ms | - |
| `bok-def-001` | 간접금융 | 3 | 95 | supported | PASS | 20375ms | - |
| `bok-def-002` | 직접금융 | 1 | 95 | supported | PASS | 21052ms | - |
| `bok-def-002` | 직접금융 | 2 | 95 | supported | PASS | 17406ms | - |
| `bok-def-002` | 직접금융 | 3 | 95 | supported | PASS | 21600ms | - |
| `bok-def-003` | 경기조절정책 | 1 | 80 | unsupported | FAIL | 24997ms | 후보 정의는 경기조절정책의 목적과 총수요 조절이라는 일반적인 방식을 정확하게 설명하고 있습니다. 그러나 원문은 실제 운영에 사용되는 구체적인 방식(재정정책과 통화정책, 그리고 각 정책의 수단)을 상세히 제시하고 있는데, 후보 정의는 이러한 핵심적인 정책 수단에 대한 설명을 생략하여 원문의 내용을 충분히 반영하지 못하고 있습니다. 이는 원문이 제시한 정책의 '방식'을 일부만 포함한 것으로 판단됩니다. |
| `bok-def-003` | 경기조절정책 | 2 | 95 | supported | PASS | 22188ms | - |
| `bok-def-003` | 경기조절정책 | 3 | 95 | supported | PASS | 21920ms | - |
| `bok-def-004` | 경제활동인구 | 1 | 95 | supported | PASS | 21408ms | - |
| `bok-def-004` | 경제활동인구 | 2 | 0 | unsupported | FAIL | 5688ms | ValidationError: 1 validation error for DictionaryDraft example   Field required [type=missing, input_value={'definition': '경제활... 'term_type': 'finance'}, input_type=dict]     For further information visit https://errors.pydantic.dev/2.13/v/missing |
| `bok-def-004` | 경제활동인구 | 3 | 100 | supported | PASS | 12389ms | - |
| `bok-def-005` | 비경제활동인구 | 1 | 95 | supported | PASS | 18986ms | - |
| `bok-def-005` | 비경제활동인구 | 2 | 98 | supported | PASS | 21159ms | - |
| `bok-def-005` | 비경제활동인구 | 3 | 95 | supported | PASS | 26217ms | - |

## 현재 게이트 판정

**HOLD** — 실패 후보를 사람이 검토하고 생성·검증 규칙을 보완해야 합니다.
