# 한국은행 원문 기반 인라인 용어 사전 운영 가이드

이 기능은 별도의 네 번째 학습 콘텐츠를 만들지 않는다. 뉴스 학습 본문에서 어려운 경제
용어가 처음 등장할 때만 밑줄을 표시하고, 사용자가 원할 때 짧은 설명을 확인하게 한다.

## 1. 데이터 구조

원문과 화면용 설명은 분리한다.

| 저장 위치 | 내용 | AI 수정 여부 |
| --- | --- | --- |
| `dictionary_source_entries` | 한국은행 원문, 원문 페이지, 개별 용어 분리 계획, 해시 | 원문은 수정하지 않음 |
| `dictionary_terms` | 개별 용어, 용어별 별칭, 주린이용 1~3문장 설명 | 있음 |

`dictionary_terms.source_entry_id`가 두 데이터를 연결한다. 따라서 화면용 설명에 문제가
있어도 공식 원문은 그대로 남고, 사용자는 한국은행 PDF의 해당 쪽을 직접 열 수 있다.

복합 원문은 `dictionary_source_entries.term_units`에 검수 상태와 함께 분리 계획을
보관한다. 여러 `dictionary_terms` 행이 같은 `source_entry_id`를 참조하며,
`source_unit_index`로 원문 안의 개별 용어 순서를 구분한다.

```text
단리/복리 원문(source entry 10)
  ├─ unit 0: 단리  aliases=[]
  └─ unit 1: 복리  aliases=[]
```

`환매조건부매매/RP/Repo`처럼 같은 개념의 다른 표기는 화면용 용어 하나와 그 용어의
`aliases`로 저장한다. 원문 항목 전체의 별칭을 모든 개별 용어가 공유하지 않는다.

복합 제목 분리 제안은 다음 네 관계 중 하나를 사용한다.

| 관계 | 의미 | 예시 |
| --- | --- | --- |
| `distinct_concepts` | 각각 검색·설명해야 하는 별도 개념 | `단리/복리` |
| `aliases` | 같은 개념의 정식명칭·약어·다른 표기 | `환매조건부매매/RP/Repo` |
| `notation` | slash가 약어 또는 통화쌍 표기의 일부 | `산업연관표(I/O Tables)` |
| `single` | 복합 구분자가 없는 단일 개념 | `빅테크` |

괄호 밖 slash가 없는 항목은 코드가 먼저 `single` 또는 `notation`으로 판정한다. 나머지
복합 제목만 공식 원문과 함께 분리 모델에 전달하며, 제안된 용어와 별칭이 원문에 실제로
등장하는지는 다시 코드로 검사한다. 이 단계의 결과는 제안일 뿐이며 검수 승인 전에는
본문에 노출하지 않는다.

공식 출처:

- [한국은행 경제금융용어 800선 안내 페이지](https://www.bok.or.kr/portal/bbs/B0000249/view.do?depth=200765&menuNo=200765&nttId=10096081&oldMenuNo=201150&programType=newsData&relate=Y)
- [한국은행 경제금융용어 800선 PDF](https://www.bok.or.kr/fileSrc/portal/5cbf35f51f3842dd9ed1fba7cef5199a/1/74ac2f04b15c4debac64fd6931aea9fd.pdf)

## 2. 최초 실행

아래 명령은 `jangdokdae-server` 폴더에서 실행한다.

```bash
uv sync --frozen
uv run python -m alembic upgrade head
uv run python scripts/import_bok_dictionary.py
```

마지막 명령은 공식 PDF를 `/tmp/jangdokdae-bok-800.pdf`에 내려받고 원문을 저장한다.
2026년 7월 현재 파서는 789개 원문 항목을 추출한다. 책 제목의 “800선”과 DB 행 수가
다른 이유는 `/`로 묶인 용어 등이 책에서 한 항목으로 설명되기 때문이다.

이미 PDF가 있다면 다음처럼 재사용할 수 있다.

```bash
uv run python scripts/import_bok_dictionary.py --pdf /tmp/bok-800.pdf
```

이 명령은 여러 번 실행해도 같은 출처·버전·용어를 갱신하는 upsert 방식이다. 기존
`dictionary_terms` 정의를 원문 가져오기만으로 덮어쓰지 않는다.

## 3. 대상 확인

DB를 쓰지 않고 파싱 결과와 선택 용어만 보려면 다음을 실행한다.

```bash
uv run python scripts/import_bok_dictionary.py \
  --pdf /tmp/bok-800.pdf \
  --dry-run
```

화면용 설명 생성 대상은 현재 `issue_docent` 제목·본문에 실제로 등장하는 한국은행
원문만 사용한다. 기존 `dictionary_terms`의 레거시 용어는 대상 선정에 사용하지 않는다.

두 글자짜리 일반 단어는 자동 탐색에서 제외해 모든 “금리”에 밑줄이 생기는 문제를
막는다. 콘텐츠 생성기가 `term_spans`로 직접 지정한 용어는 예외로 취급한다.

## 4. 화면용 AI 설명 생성

먼저 한 항목으로 생성과 검증을 확인한다.

```bash
uv run python scripts/import_bok_dictionary.py \
  --pdf /tmp/bok-800.pdf \
  --generate \
  --term 빅테크 \
  --limit 1
```

기존 정의를 검증 통과한 새 정의로 교체하려면 `--overwrite-existing`을 추가한다.

```bash
uv run python scripts/import_bok_dictionary.py \
  --pdf /tmp/bok-800.pdf \
  --generate \
  --term 국채선물 \
  --limit 1 \
  --overwrite-existing
```

선택된 용어를 여러 개 처리할 때는 `--term`을 빼고 `--limit`을 늘린다.

```bash
uv run python scripts/import_bok_dictionary.py \
  --generate \
  --limit 20 \
  --overwrite-existing
```

`DICTIONARY_GROUNDED_MODEL`을 따로 설정하지 않으면 뉴스 파이프라인에서 이미 검증된
`VERTEX_MODEL`을 사용한다. 한 항목마다 생성 1회와 검증 1회의 Vertex AI 호출이 발생한다.

## 5. 품질 게이트

설명은 다음 단계를 모두 통과해야 `approved`로 저장된다.

1. 생성 모델은 해당 용어의 한국은행 원문만 입력으로 받는다.
2. 코드가 문장 길이, 문장 수, 투자 권유 문구, 원문에 없는 숫자를 검사한다.
3. 별도 검증 호출이 모든 주장의 원문 근거, 가독성, 맞춤법을 평가한다.
4. `supported=true`이며 80점 이상인 결과만 승인한다.
5. 탈락하거나 호출에 실패하면 기존 승인 설명을 변경하지 않는다.

AI 검증도 맞춤법을 완벽히 잡는 것은 아니므로, 여러 건을 한꺼번에 공개하기 전에
`GET /api/v1/dictionary?status=approved` 결과를 표본 검수한다. 화면에는 “AI가 정리한
설명 · 한국은행 원문 기반” 문구와 원문 링크가 함께 표시된다.

## 6. 본문 노출 규칙

Issue Detail API는 한국은행 원문을 기반으로 생성되고 검증을 통과한 용어 중 본문에
실제로 등장하는 용어를 다시 찾는다. 기존 `source=llm`,
`verification_status=legacy` 용어는 보관만 하며 런타임 매칭에서 제외한다.

- 한 이슈당 최대 5개
- 본문 등장 순
- 같은 용어는 전체 카드에서 첫 등장 한 번만 밑줄 표시
- 데스크톱: hover 또는 키보드 focus 시 짧은 tooltip
- 모바일: tap 시 하단 상세 sheet
- 상단 “용어 N” 버튼: 해당 이슈의 전체 용어 목록

공식 원문을 기반으로 검증된 항목만 한국은행 출처 배지와 PDF 쪽 링크를 받는다. 기존
레거시 설명에 원문 행만 연결된 상태라면 출처 기반 설명인 것처럼 표시하지 않는다.

## 7. 현재 운영 원칙과 후속 TODO

- 원문 가져오기는 배포 또는 수동 유지보수 작업으로 실행한다.
- 뉴스 수집 GitHub Actions의 성공 여부와 사전 생성 성공 여부는 분리한다.
- 사전 생성 실패 때문에 오늘의 뉴스 콘텐츠 생성이 실패해서는 안 된다.
- 다음 단계에서는 관리자 검수 화면, 생성 시도 이력, 원문 버전 변경 알림을 추가한다.
- 용어가 늘어 API 조회 비용이 커지면 승인 사전을 프로세스 캐시하거나 matcher 결과를
  `issue_docent` 후처리 결과로 저장한다.
