# 용어 분리 평가 Task

`segmentation_gold.jsonl`은 한국은행 「경제금융용어 800선」 원문에서 뽑은 승인 골드
라벨이다. 2026년 7월 20일 프로젝트 소유자가 각 관계, 대표 용어, 별칭을 검수했다.

- `content_hash`는 `source_term + 줄바꿈 + raw_definition`의 SHA-256이다.
- 새 Task는 `label_status=draft`로 추가하며 기본 로더가 이를 거부한다.
- 사람이 `expected`를 검수한 뒤에만 `approved`로 바꾸고 `reviewed_by`,
  `reviewed_at`을 기록한다. 현재 파일의 13개 Task는 이 검수를 완료했다.
- 모델 출력이나 DB의 기존 `term_units`를 정답으로 복사하지 않는다.

현재 골드셋은 네 관계를 모두 포함한다.

| ID | 원문 제목 | 승인 관계 |
| --- | --- | --- |
| `bok-seg-001` | 단리/복리 | `distinct_concepts` |
| `bok-seg-002` | 명목금리/실질금리 | `distinct_concepts` |
| `bok-seg-003` | 환매조건부매매/RP/Repo | `aliases` |
| `bok-seg-004` | 산업연관표(I/O Tables) | `notation` |
| `bok-seg-005` | 빅테크 | `single` |
| `bok-seg-006` | 간접금융/직접금융 | `distinct_concepts` |
| `bok-seg-007` | 경기조절정책/경제안정화정책 | `aliases` |
| `bok-seg-008` | 경제활동인구/비경제활동인구/경제활동참가율 | `distinct_concepts` |
| `bok-seg-009` | 노동생산성/노동생산성지수 | `distinct_concepts` |
| `bok-seg-010` | 리스크 온(Risk On)/오프(Off) | `distinct_concepts` |
| `bok-seg-011` | 매입외환/환가료 | `distinct_concepts` |
| `bok-seg-012` | 바젤은행감독위원회/바젤위원회(BCBS) | `aliases` |
| `bok-seg-013` | 원/위안 직거래시장 | `notation` |
