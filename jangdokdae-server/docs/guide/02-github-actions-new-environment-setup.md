# GitHub Actions 운영 전환 및 신규 환경 구축 가이드

이 문서는 장독대 뉴스 파이프라인을 개인 노트북의 Airflow 대신 GitHub Actions에서 정기
실행하기 위해, 사용자가 직접 해야 하는 설정을 처음부터 안내합니다.

기존 서버·DB·Google Cloud 설정은 재사용하지 않고 다음 환경을 새로 만든다고 가정합니다.

- GitHub 저장소: `subeomsp/jangdokdae`
- 데이터베이스: 새 Neon PostgreSQL 프로젝트
- LLM: 새 Google Cloud 프로젝트의 Vertex AI
- 실행기: GitHub-hosted Actions runner
- API 서버: 당장은 만들지 않으며, 프론트엔드 연결 시 별도로 배포

> 중요: 비밀번호, DB 주소, API 키, 서비스 계정 JSON을 이 문서·Git 커밋·이슈·채팅에
> 붙여 넣지 마세요. 이 문서에서 “복사”라고 하는 값은 비밀번호 관리자, 로컬 `.env`,
> GitHub Actions Secrets 중 지정된 위치에만 넣습니다.

## 1. 완성 후 구조

```text
GitHub Actions (하루 2~4회, 필요할 때 수동 실행 가능)
  └─ 기존 services.pipeline.runner 실행
       ├─ RSS 뉴스 및 DART 공시 수집
       ├─ 전처리
       ├─ Hugging Face 임베딩
       ├─ HDBSCAN 클러스터링 및 주요 이슈 선정
       ├─ Vertex AI Gemini 분석·콘텐츠 생성
       └─ Neon PostgreSQL + pgvector 저장
```

Airflow DAG와 Docker Compose 코드는 삭제하지 않습니다. 나중에 파이프라인이 더 복잡해지거나
상시 서버를 마련하면 다시 Airflow로 전환할 수 있습니다.

GitHub Actions는 배치 작업만 실행합니다. FastAPI 서버를 24시간 제공하는 서비스가 아니므로,
프론트엔드가 생겼을 때는 API 서버를 Cloud Run 등에 별도로 배포해야 합니다.

## 2. 전체 체크리스트

아래 순서대로 진행합니다. 순서를 바꾸면 인증 또는 빈 테이블 문제로 첫 실행이 실패할 수 있습니다.

- [ ] 새 Neon 프로젝트 생성
- [ ] Neon의 직접 연결 주소와 pooled 연결 주소를 각각 보관
- [ ] 새 로컬 `.env` 작성
- [ ] 새 DB에 Alembic 마이그레이션 적용
- [ ] 섹터 기본 데이터 11개 입력
- [ ] OpenDART·ECOS·KRX 계정 또는 API 키 준비
- [ ] 국내·해외 기업 마스터 초기화
- [ ] 새 Google Cloud 프로젝트 생성 및 결제 계정 연결
- [ ] Vertex AI와 인증 관련 API 활성화
- [ ] GitHub Actions용 Workload Identity Federation 설정
- [ ] GitHub 저장소 Variables와 Secrets 등록
- [ ] GitHub Actions 워크플로 파일을 기본 브랜치 `main`에 병합
- [ ] 수동으로 첫 실행 후 DB 결과 확인
- [ ] 이상이 없으면 정기 스케줄 활성화

## 3. 작업 중 기록할 값

아래 표는 체크 용도입니다. 실제 비밀값은 표에 적지 말고 비밀번호 관리자에 보관하세요.

| 항목 | 예시 | 비밀 여부 |
|---|---|---:|
| GitHub 저장소 | `subeomsp/jangdokdae` | 아니요 |
| Neon 프로젝트 이름 | `jangdokdae-production` | 아니요 |
| Neon 리전 | 선택한 가장 가까운 리전 | 아니요 |
| Neon direct URL | `postgresql://...` | **비밀** |
| Neon pooled URL | 호스트에 `-pooler`가 포함된 `postgresql://...` | **비밀** |
| Google Cloud 프로젝트 ID | 직접 정한 전역 고유 ID | 아니요 |
| Google Cloud 프로젝트 번호 | 숫자로만 된 값 | 아니요 |
| WIF Provider 이름 | `projects/숫자/.../providers/github` | 아니요 |
| 서비스 계정 이메일 | `github-actions-jangdokdae@...iam.gserviceaccount.com` | 아니요 |

## 4. 새 Neon 데이터베이스 만들기

### 4.1 프로젝트 생성

1. [Neon Console](https://console.neon.tech)에 로그인합니다.
2. `New Project` 또는 `Create project`를 누릅니다.
3. 프로젝트 이름을 `jangdokdae-production`처럼 알아보기 쉽게 입력합니다.
4. PostgreSQL 버전은 Neon의 현재 기본값을 사용합니다.
5. 리전은 GitHub Actions와 Google Cloud에서 접근하기 가까운 아시아 리전을 우선 선택합니다.
6. 프로젝트 생성을 완료합니다.

### 4.2 연결 주소 두 개 복사

프로젝트 대시보드에서 `Connect`를 누릅니다.

먼저 `Connection pooling`을 끈 상태에서 `Connection string`을 복사합니다. 이것이 **direct
URL**이며 최초 마이그레이션에 사용합니다.

```text
postgresql://<DB_USER>:<DB_PASSWORD>@<DIRECT_HOST>/<DB_NAME>?sslmode=require
```

그다음 `Connection pooling`을 켜고 다시 연결 주소를 복사합니다. 호스트 이름에 보통
`-pooler`가 포함됩니다. 이것이 **pooled URL**이며 GitHub Actions와 향후 API 서버에서 사용합니다.

```text
postgresql://<DB_USER>:<DB_PASSWORD>@<POOLED_HOST>/<DB_NAME>?sslmode=require
```

두 주소를 다음 이름으로 비밀번호 관리자에 보관합니다.

- `JANGDOKDAE_DATABASE_URL_DIRECT`
- `JANGDOKDAE_DATABASE_URL_POOLED`

연결 주소 전체에 DB 비밀번호가 들어 있으므로 스크린샷을 공유하거나 Git에 올리면 안 됩니다.

## 5. 새 로컬 `.env` 준비

명령은 터미널에서 내려받은 저장소의 루트로 이동한 뒤 서버 디렉터리에서 실행합니다.

```bash
cd jangdokdae-server
```

기존 `.env`를 보존해야 한다면 먼저 이름을 바꿉니다.

```bash
cp .env .env.previous.local
```

`.env.previous.local`도 비밀 파일입니다. 현재 `.gitignore`에 포함되는 이름이므로 반드시 이
이름을 사용합니다.

새 템플릿을 복사합니다.

```bash
cp .env.example .env
```

에디터로 `.env`를 열고 우선 아래 항목만 새 값으로 채웁니다.

```env
# 최초 마이그레이션 때는 Neon direct URL 사용
DATABASE_URL=여기에_JANGDOKDAE_DATABASE_URL_DIRECT

# 아래 명령으로 새로 생성한 값
SECRET_KEY=새로_생성한_64자리_문자열

GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=asia-northeast3
VERTEX_MODEL=gemini-2.5-flash

OPENDART_API_KEY=
ECOS_API_KEY=
KRX_ID=
KRX_PW=
```

`SECRET_KEY`는 기존 서버 값을 복사하지 말고 새로 생성합니다.

```bash
openssl rand -hex 32
```

출력된 한 줄 전체를 `.env`의 `SECRET_KEY=` 오른쪽에 붙여 넣습니다. 이 값은 나중에
GitHub Secret에도 동일하게 등록합니다.

OAuth, 쿠키, CORS 설정은 뉴스 배치 파이프라인에는 필요하지 않습니다. API 서버를 배포할 때
별도로 설정합니다.

## 6. 새 DB 스키마 만들기

### 6.1 의존성 설치

```bash
uv sync --extra dev
```

### 6.2 마이그레이션 head 확인

```bash
uv run alembic heads
```

현재 코드 기준 정상 출력은 다음 하나입니다.

```text
a4c6e8f0b2d4 (head)
```

head가 둘 이상 나오면 마이그레이션을 실행하지 말고 코드 상태를 먼저 확인합니다.

### 6.3 마이그레이션 적용

다음 명령은 `.env`의 `DATABASE_URL`이 가리키는 DB에 테이블을 생성합니다. 반드시 새 Neon
프로젝트의 direct URL인지 다시 확인합니다.

```bash
uv run alembic upgrade head
```

baseline 마이그레이션이 `pgvector` 확장도 함께 활성화하므로 Neon SQL Editor에서 별도로
`CREATE EXTENSION`을 실행할 필요는 없습니다.

완료 후 확인합니다.

```bash
uv run alembic current
```

정상 출력:

```text
a4c6e8f0b2d4 (head)
```

### 6.4 런타임 DB 주소로 변경

마이그레이션이 끝나면 `.env`의 `DATABASE_URL`을 Neon **pooled URL**로 교체합니다.

```env
DATABASE_URL=여기에_JANGDOKDAE_DATABASE_URL_POOLED
```

GitHub Actions에도 이 pooled URL을 등록합니다.

## 7. 섹터 기본 데이터 넣기

새 DB의 `sectors` 테이블은 스키마만 있고 기본 행은 없습니다. 기업 마스터를 동기화하기 전에
Neon Console의 `SQL Editor`에서 아래 SQL을 한 번 실행합니다.

```sql
INSERT INTO sectors (name_ko, name_en, wics_code, gics_code)
VALUES
    ('에너지', 'Energy', '10', '10'),
    ('소재', 'Materials', '15', '15'),
    ('산업재', 'Industrials', '20', '20'),
    ('경기소비재', 'Consumer Discretionary', '25', '25'),
    ('필수소비재', 'Consumer Staples', '30', '30'),
    ('헬스케어', 'Health Care', '35', '35'),
    ('금융', 'Financials', '40', '40'),
    ('IT', 'Information Technology', '45', '45'),
    ('커뮤니케이션서비스', 'Communication Services', '50', '50'),
    ('유틸리티', 'Utilities', '55', '55'),
    ('부동산', 'Real Estate', 'NA', '60')
ON CONFLICT DO NOTHING;
```

확인 SQL:

```sql
SELECT id, name_ko, gics_code FROM sectors ORDER BY id;
```

11행이 나오면 정상입니다.

## 8. 외부 데이터 계정과 API 키 만들기

### 8.1 OpenDART API 키 — 필수

OpenDART는 국내 공시와 기업 코드를 가져올 때 사용합니다.

1. [OpenDART 인증키 신청](https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do)에 접속합니다.
2. 개인 프로젝트라면 사용자 구분에서 `개인`을 선택합니다.
3. 이메일, 비밀번호, API 사용환경과 사용용도를 입력합니다.
4. 가입 또는 신청을 완료합니다.
5. OpenDART의 `계정관리 → 인증키 관리`에서 발급된 키를 확인합니다.
6. 키 전체를 복사해 비밀번호 관리자에 `JANGDOKDAE_OPENDART_API_KEY`로 보관합니다.
7. 로컬 `.env`의 `OPENDART_API_KEY=` 오른쪽에 붙여 넣습니다.

사용용도 예시:

```text
개인 개발 프로젝트의 상장사 공시 및 재무정보 수집
```

### 8.2 한국은행 ECOS API 키 — 월간 거시지표를 사용할 때 필수

1. [ECOS Open API](https://ecos.bok.or.kr/api/#/)에 접속합니다.
2. 회원가입 또는 로그인합니다.
3. 인증키 신청 메뉴에서 이메일과 사용 목적을 입력합니다.
4. 발급된 키를 복사합니다.
5. 비밀번호 관리자에 `JANGDOKDAE_ECOS_API_KEY`로 보관합니다.
6. 로컬 `.env`의 `ECOS_API_KEY=` 오른쪽에 붙여 넣습니다.

사용목적 예시:

```text
뉴스 콘텐츠의 거시경제 배경정보 제공을 위한 기준금리·CPI·M2 수집
```

ECOS를 아직 신청하지 않아도 뉴스 파이프라인 자체는 만들 수 있지만, 월간 거시지표 워크플로는
실행하지 않아야 합니다.

### 8.3 KRX 계정 — 국내 기업 마스터 초기화 시 필요

현재 기업 마스터 초기화 스크립트는 PyKRX를 사용하며 KRX 로그인 계정을 요구합니다.

1. [KRX Data Marketplace](https://data.krx.co.kr)에 접속합니다.
2. 회원가입 후 로그인 가능한지 확인합니다.
3. 로그인 ID와 비밀번호를 비밀번호 관리자에 보관합니다.
4. 로컬 `.env`의 `KRX_ID=`, `KRX_PW=`에 입력합니다.

KRX 로그인 정보를 GitHub에 등록하는 것은 기업 마스터를 Actions에서 주기적으로 갱신할 때만
필요합니다. 최초 1회 로컬 초기화만 한다면 GitHub Secret으로 올리지 않아도 됩니다.

## 9. 기업 마스터 초기화

뉴스만 수집하는 것은 기업 마스터 없이도 가능하지만, DART 공시·기업 태깅·섹터 연결 품질이
떨어집니다. 전체 파이프라인을 사용하려면 초기화하는 것을 권장합니다.

### 9.1 국내 상장사 및 KOSPI200 활성화

`.env`에 새 DB pooled URL, OpenDART 키, KRX ID/PW가 들어 있는지 확인한 후 실행합니다.

```bash
uv run python -m scripts.sync_company_master
```

정상적으로 끝나면 전체 상장사가 `company_entities`에 들어가고 KOSPI200 종목이
`is_active=True`로 활성화됩니다.

### 9.2 해외 종목 초기화

```bash
uv run python -m scripts.sync_overseas_companies
```

이 작업은 S&P 500, NASDAQ-100, 주요 미국 ETF 데이터를 적재합니다.

### 9.3 Neon에서 확인

Neon SQL Editor에서 실행합니다.

```sql
SELECT count(*) AS all_companies FROM company_entities;
SELECT count(*) AS active_companies FROM company_entities WHERE is_active = true;
SELECT market, count(*) FROM company_entities GROUP BY market ORDER BY market;
```

전체 또는 활성 기업이 0이면 GitHub Actions를 켜기 전에 기업 동기화 로그를 확인합니다.

## 10. 새 Google Cloud 프로젝트 만들기

### 10.1 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com)에 로그인합니다.
2. 상단 프로젝트 선택기에서 `새 프로젝트`를 누릅니다.
3. 프로젝트 이름을 `jangdokdae-production`처럼 입력합니다.
4. 프로젝트 ID는 전 세계에서 고유해야 합니다. 자동 생성값을 사용하거나 직접 정합니다.
5. 프로젝트 생성 후 상단 프로젝트 선택기에서 새 프로젝트를 선택합니다.
6. `결제 → 결제 계정 연결`에서 결제 계정을 연결합니다.

프로젝트 대시보드에 표시되는 **프로젝트 ID**를 복사해 기록합니다. 프로젝트 이름과 프로젝트
ID는 다릅니다. 아래 명령에는 프로젝트 ID가 필요합니다.

프로젝트를 만든 뒤 로컬 `.env`에도 새 프로젝트 ID를 입력합니다. 기존
`app/credentials/vertex_key.json` 경로는 재사용하지 않습니다.

```env
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_CLOUD_PROJECT=여기에_새_Google_Cloud_프로젝트_ID
GOOGLE_CLOUD_LOCATION=asia-northeast3
VERTEX_MODEL=gemini-2.5-flash
```

### 10.2 Cloud Shell 열기

Google Cloud Console 오른쪽 위의 터미널 모양 `Cloud Shell 활성화` 버튼을 누릅니다. 별도 설치
없이 `gcloud` 명령을 실행할 수 있습니다.

아래 첫 줄의 값만 새 프로젝트 ID로 바꾼 후 블록 전체를 Cloud Shell에 붙여 넣습니다.

```bash
export PROJECT_ID="여기에_새_Google_Cloud_프로젝트_ID"
export GITHUB_REPOSITORY="subeomsp/jangdokdae"
export POOL_ID="github-actions"
export PROVIDER_ID="github"
export SERVICE_ACCOUNT_NAME="github-actions-jangdokdae"

gcloud config set project "$PROJECT_ID"
gcloud projects describe "$PROJECT_ID" --format='value(projectId)'
```

마지막 줄에 입력한 프로젝트 ID가 그대로 나오면 다음 단계로 진행합니다.

### 10.3 필요한 API 활성화

Cloud Shell에서 실행합니다.

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  sts.googleapis.com
```

권한 오류가 나오면 현재 Google 계정이 해당 프로젝트의 Owner이거나 API 활성화 권한을
보유했는지 `IAM 및 관리자 → IAM`에서 확인합니다.

### 10.4 GitHub Actions용 서비스 계정 생성

```bash
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name="Jangdokdae GitHub Actions"

export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/aiplatform.user"
```

이 서비스 계정은 Vertex AI 호출 권한만 갖습니다. 프로젝트 Owner 또는 Editor 역할을 부여하지
마세요.

## 11. Workload Identity Federation 설정

이 방식은 서비스 계정 JSON 키를 GitHub에 보관하지 않고, 각 Actions 실행 시 짧게 유효한
Google 인증을 발급합니다. Google과 GitHub가 권장하는 방식입니다.

### 11.1 Workload Identity Pool 생성

```bash
gcloud iam workload-identity-pools create "$POOL_ID" \
  --location="global" \
  --display-name="GitHub Actions"

export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
```

### 11.2 GitHub OIDC Provider 생성

아래 조건은 `subeomsp/jangdokdae` 저장소에서 발급된 토큰만 허용합니다.

```bash
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub subeomsp/jangdokdae" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='${GITHUB_REPOSITORY}'"
```

### 11.3 저장소가 서비스 계정을 사용할 수 있게 연결

```bash
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}"
```

### 11.4 GitHub에 복사할 값 출력

```bash
echo "GCP_PROJECT_ID=${PROJECT_ID}"
echo "GCP_WIF_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"
echo "GCP_SERVICE_ACCOUNT=${SERVICE_ACCOUNT_EMAIL}"
```

출력된 세 줄을 메모장에 잠시 복사합니다. 이 값들은 비밀번호는 아니지만, 다음 단계에서 GitHub
Repository Variables로 등록합니다.

설정 직후에는 Google IAM 전파에 몇 분이 걸릴 수 있습니다. 첫 인증이 실패하면 5분 정도 후
다시 실행합니다.

### 11.5 로컬에서도 Vertex AI를 시험하고 싶을 때만 수행

GitHub Actions는 앞에서 만든 Workload Identity를 사용하므로 이 단계가 필요 없습니다. 로컬
터미널에서 Gemini까지 시험하려는 경우에만 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)를
설치한 뒤 실행합니다.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project 여기에_새_Google_Cloud_프로젝트_ID
```

브라우저가 열리면 새 Google Cloud 프로젝트에 접근할 수 있는 본인 계정으로 로그인합니다.
서비스 계정 JSON 파일을 내려받을 필요는 없습니다.

## 12. GitHub Actions Variables 등록

1. [GitHub 저장소](https://github.com/subeomsp/jangdokdae)에 접속합니다.
2. 저장소 상단 `Settings`를 누릅니다.
3. 왼쪽 메뉴에서 `Secrets and variables → Actions`를 누릅니다.
4. `Variables` 탭을 선택합니다.
5. `New repository variable`을 눌러 아래 항목을 하나씩 등록합니다.

| Variable 이름 | 넣을 값 |
|---|---|
| `GCP_PROJECT_ID` | Cloud Shell에서 출력한 `GCP_PROJECT_ID` 값 |
| `GCP_WIF_PROVIDER` | `projects/숫자/locations/global/.../providers/github` 전체 |
| `GCP_SERVICE_ACCOUNT` | `github-actions-jangdokdae@프로젝트ID.iam.gserviceaccount.com` |
| `GOOGLE_CLOUD_LOCATION` | `asia-northeast3` |
| `VERTEX_MODEL` | `gemini-2.5-flash` |
| `EMBED_MODEL` | `jhgan/ko-sroberta-multitask` |

변수 이름의 철자와 대소문자를 그대로 사용합니다.

## 13. GitHub Actions Secrets 등록

같은 화면에서 `Secrets` 탭으로 이동한 후 `New repository secret`을 누릅니다.

### 13.1 반드시 등록할 Secret

| Secret 이름 | 어디에서 복사하는가 | 설명 |
|---|---|---|
| `DATABASE_URL` | Neon의 `JANGDOKDAE_DATABASE_URL_POOLED` | pooled URL 전체 |
| `SECRET_KEY` | 새 로컬 `.env`의 `SECRET_KEY` 오른쪽 값 | `openssl rand -hex 32` 결과 |
| `OPENDART_API_KEY` | OpenDART 인증키 관리 화면 | 일일 공시 수집 |

`DATABASE_URL`은 `postgresql://`부터 쿼리 문자열 끝까지 전체를 복사합니다. 따옴표는 넣지
않습니다.

### 13.2 기능에 따라 등록할 Secret

| Secret 이름 | 필요한 시점 |
|---|---|
| `ECOS_API_KEY` | 월간 거시지표 워크플로를 실행할 때 |
| `KRX_ID` | 기업 마스터를 Actions에서 갱신할 때 |
| `KRX_PW` | 기업 마스터를 Actions에서 갱신할 때 |
| `DICTIONARY_ADMIN_TOKEN` | 향후 사전 관리 API를 배포할 때 |

Workload Identity Federation을 사용하므로 다음 값은 등록하지 않습니다.

- `GOOGLE_APPLICATION_CREDENTIALS`
- 로컬 `vertex_key.json` 파일 내용
- 서비스 계정 JSON 키

GitHub Secret은 저장 후 값을 다시 보여주지 않습니다. 오타가 의심되면 같은 이름으로 다시
등록하여 덮어씁니다.

## 14. GitHub Actions 사용 허용

GitHub 저장소의 `Settings → Actions → General`로 이동합니다.

1. `Actions permissions`에서 저장소 워크플로 실행이 허용되어 있는지 확인합니다.
2. 조직 정책이 없다면 GitHub 공식 Action과 Google 인증 Action을 사용할 수 있도록 설정합니다.
3. `Workflow permissions`는 기본 `Read repository contents permission`이면 충분합니다.
4. 저장합니다.

워크플로 자체에는 아래 권한만 줄 예정입니다.

```yaml
permissions:
  contents: read
  id-token: write
```

`id-token: write`는 저장소 내용을 수정하는 권한이 아니라 Google의 단기 인증 토큰을 받기 위한
권한입니다.

## 15. 워크플로를 기본 브랜치에 넣기

GitHub의 예약 실행(`schedule`)은 기본 브랜치에 있는 워크플로만 실행합니다.

현재 파이프라인 통합 결과는 `fix/pipeline-sync` 브랜치에 있으므로 다음 순서가 필요합니다.

1. [파이프라인 PR 생성 화면](https://github.com/subeomsp/jangdokdae/pull/new/fix/pipeline-sync)을 엽니다.
2. base가 `main`, compare가 `fix/pipeline-sync`인지 확인합니다.
3. 변경 파일과 테스트 결과를 확인합니다.
4. PR을 생성하고 `main`에 병합합니다.
5. GitHub Actions 워크플로 파일이 추가된 후에도 해당 파일을 `main`에 병합합니다.

> 현재 문서를 작성한 시점에는 GitHub Actions 워크플로 파일을 아직 추가하지 않았습니다.
> `.github/workflows/news-pipeline.yml` 구현과 테스트는 코드 작업 단계에서 별도로 진행합니다.
> 이 문서의 Variables/Secrets 이름과 동일하게 구현해야 합니다.

## 16. 첫 실행 전 최종 점검

GitHub 저장소에서 다음을 확인합니다.

- `Settings → Secrets and variables → Actions → Variables`에 GCP 변수 6개가 있음
- 같은 화면의 `Secrets`에 `DATABASE_URL`, `SECRET_KEY`, `OPENDART_API_KEY`가 있음
- Google Cloud 프로젝트에 결제 계정이 연결됨
- Vertex AI API가 활성화됨
- 새 Neon DB의 Alembic 리비전이 `a4c6e8f0b2d4`
- `sectors`가 11행임
- `company_entities`의 활성 기업이 1개 이상임
- 워크플로 파일이 기본 브랜치 `main`에 있음

## 17. 첫 수동 실행 및 확인

워크플로 파일이 추가된 후 GitHub 저장소 상단 `Actions` 탭으로 이동합니다.

1. 왼쪽에서 `Jangdokdae News Pipeline`을 선택합니다.
2. `Run workflow`를 누릅니다.
3. 브랜치는 `main`을 선택합니다.
4. 세션을 고르는 입력이 있으면 첫 실행은 `morning`을 선택합니다.
5. 실행 버튼을 누릅니다.
6. 노란색은 실행 중, 초록색은 성공, 빨간색은 실패입니다.
7. 실행 항목을 눌러 각 단계의 로그를 확인합니다.

첫 실행은 Python 패키지와 Hugging Face 모델을 내려받아 이후 실행보다 오래 걸릴 수 있습니다.
Gemini 호출 비용도 발생할 수 있습니다.

성공 후 Neon SQL Editor에서 확인합니다.

```sql
SELECT count(*) FROM news;
SELECT count(*) FROM news WHERE embedding IS NOT NULL;
SELECT count(*) FROM news_cluster WHERE is_current = true;
SELECT count(*) FROM news_analysis;
SELECT count(*) FROM issue_docent;

SELECT max(created_at) AS latest_news FROM news;
SELECT max(created_at) AS latest_analysis FROM news_analysis;
```

첫 실행 직후 모든 숫자가 클 필요는 없습니다. 최소한 `news`가 1행 이상이고 실행 로그에 인증·DB
연결 오류가 없어야 합니다. 뉴스 출처 상황에 따라 분석할 클러스터가 만들어지지 않을 수도 있습니다.

## 18. 권장 실행 시각

GitHub는 매시 정각에 예약 실행 부하가 몰리면 실행이 지연될 수 있다고 안내합니다. 따라서 기존
Airflow 시각에서 7분 정도 옮기는 것을 권장합니다.

| 목적 | 기존 KST | 권장 GitHub Actions KST |
|---|---:|---:|
| 야간 뉴스 반영 | 00:00 | 00:07 |
| 장 시작 | 09:00 | 09:07 |
| 점심 | 12:00 | 12:07 |
| 장 마감 | 15:30 | 15:37 |

초기 1~2주는 `09:07`, `15:37` 하루 2회만 운영하고 실행시간과 비용을 확인한 뒤 하루 4회로
늘리는 편이 안전합니다.

비공개 저장소의 GitHub Free 한도가 월 2,000분이라고 가정하면 하루 4회는 월 약 120회입니다.
평균 실행시간이 약 16분 40초를 넘으면 무료 한도를 초과할 수 있습니다. Actions의 각 실행에서
`Usage`를 확인해 실제 사용량을 측정합니다.

## 19. API 서버는 언제 만들면 되는가

뉴스를 수집하고 콘텐츠를 DB에 만드는 데는 상시 API 서버가 필요하지 않습니다. GitHub Actions가
Neon과 Vertex AI에 직접 연결합니다.

프론트엔드가 다음 API를 호출해야 할 때 FastAPI 서버를 배포합니다.

- 이슈 목록 및 상세 조회
- 로그인/OAuth
- 북마크, 사용자 관심사, 퀴즈 결과 저장
- 용어 사전 조회

그때는 같은 Google Cloud 프로젝트의 Cloud Run을 우선 권장합니다. API 서버 배포 시 추가로
준비할 값은 다음과 같습니다.

| 항목 | 설명 |
|---|---|
| `DATABASE_URL` | 같은 Neon pooled URL |
| `SECRET_KEY` | GitHub Actions와 동일한 신규 값 또는 별도 운영용 값 |
| `CORS_ORIGINS` | 실제 프론트엔드 주소 |
| `FRONTEND_BASE_URL` | OAuth 완료 후 이동할 프론트엔드 주소 |
| `COOKIE_SECURE` | HTTPS 운영에서는 `True` |
| `OAUTH_KAKAO_*` | 카카오 개발자 콘솔에서 발급 |
| `OAUTH_GOOGLE_*` | Google OAuth 클라이언트에서 발급 |

프론트엔드 도메인과 API 도메인이 정해지기 전에는 OAuth redirect URI를 확정할 수 있으므로,
현재 GitHub Actions 전환 단계에서는 만들지 않아도 됩니다.

## 20. Workload Identity 설정이 어려울 때의 임시 대안

권장 방식은 Workload Identity Federation입니다. 부득이하게 서비스 계정 JSON 키를 쓰는 경우에만
아래 대안을 사용합니다.

1. Google Cloud Console의 `IAM 및 관리자 → 서비스 계정`으로 이동합니다.
2. `github-actions-jangdokdae` 서비스 계정을 선택합니다.
3. `키 → 키 추가 → 새 키 만들기 → JSON`을 선택합니다.
4. 내려받은 JSON 파일을 열어 내용 전체를 복사합니다.
5. GitHub Secret `GCP_SERVICE_ACCOUNT_KEY`에 JSON 전체를 등록합니다.
6. JSON 파일은 Git 저장소 밖의 안전한 위치로 옮기거나, 설정 확인 후 폐기합니다.

절대 하면 안 되는 작업:

- JSON 파일을 `app/credentials`에 넣고 커밋
- JSON 내용을 `.env.example`에 붙여 넣기
- Slack, Notion 공개 페이지, GitHub Issue에 공유

이 방식은 장기 비밀키가 유출될 위험이 있으므로 임시로만 사용하고, 가능한 빨리 Workload Identity
Federation으로 교체합니다. 워크플로 코드도 `GCP_SERVICE_ACCOUNT_KEY` 방식을 지원하도록 별도
수정해야 합니다.

## 21. 자주 발생하는 오류

### `DATABASE_URL` 또는 `password authentication failed`

- GitHub Secret에 Neon URL 전체가 들어갔는지 확인합니다.
- URL 앞뒤에 따옴표나 공백을 넣지 않았는지 확인합니다.
- GitHub Actions에는 direct URL이 아닌 pooled URL을 권장합니다.
- Neon에서 DB 비밀번호를 재설정했다면 Secret도 다시 등록합니다.

### `relation ... does not exist`

- 새 DB에 `uv run alembic upgrade head`를 실행했는지 확인합니다.
- 다른 Neon 프로젝트의 연결 주소를 GitHub Secret에 넣지 않았는지 확인합니다.

### `Unable to acquire impersonated credentials`

- `GCP_WIF_PROVIDER`에 프로젝트 ID가 아니라 **프로젝트 번호**가 들어갔는지 확인합니다.
- Provider 조건의 저장소가 `subeomsp/jangdokdae`인지 확인합니다.
- 서비스 계정에 `roles/iam.workloadIdentityUser` 연결이 있는지 확인합니다.
- IAM 설정 후 5분 정도 기다렸다 다시 실행합니다.

### `403` 또는 Vertex AI 권한 오류

- Vertex AI API가 활성화되었는지 확인합니다.
- 서비스 계정에 `Vertex AI User` 역할이 있는지 확인합니다.
- `GCP_PROJECT_ID`가 새 프로젝트 ID인지 확인합니다.
- 프로젝트에 결제 계정이 연결되었는지 확인합니다.

### `Quiz/Dictionary model not found` 또는 모델 지역 오류

- 기본 뉴스 모델은 `gemini-2.5-flash`, 리전은 `asia-northeast3`입니다.
- preview 모델은 제공 리전이 바뀔 수 있습니다. 사전/퀴즈 생성에서 오류가 나면 Google Cloud의
  Vertex AI Model Garden에서 해당 프로젝트와 리전의 사용 가능 모델을 확인합니다.

### Actions 예약 실행이 보이지 않음

- 워크플로 파일이 `main`에 있는지 확인합니다.
- 저장소의 기본 브랜치가 무엇인지 확인합니다.
- `Settings → Actions → General`에서 Actions가 허용됐는지 확인합니다.
- 공개 저장소는 장기간 활동이 없으면 예약 워크플로가 자동 비활성화될 수 있습니다.

## 22. 설정을 폐기하거나 다시 만들 때

테스트가 끝나고 환경을 폐기할 경우 다음 순서로 정리합니다.

1. GitHub Actions 워크플로를 비활성화합니다.
2. GitHub Repository Secrets와 Variables를 삭제합니다.
3. Google Cloud의 Workload Identity Provider를 삭제하거나 비활성화합니다.
4. `github-actions-jangdokdae` 서비스 계정을 삭제합니다.
5. Google Cloud 결제 예산과 사용량을 확인합니다.
6. Neon 프로젝트를 삭제하기 전에 필요한 데이터를 백업합니다.
7. 로컬 `.env`, `.env.previous.local`, 서비스 계정 JSON을 안전하게 폐기합니다.

## 23. 공식 참고 문서

- [GitHub Actions 예약 실행](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Actions 제한](https://docs.github.com/en/actions/reference/limits)
- [Google Cloud: 배포 파이프라인용 Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google GitHub Auth Action](https://github.com/google-github-actions/auth)
- [Neon pooled connection](https://neon.com/docs/connect/connection-pooling)
- [Neon pgvector](https://neon.com/docs/ai/ai-concepts)
- [OpenDART 인증키 신청](https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do)
- [한국은행 ECOS Open API](https://ecos.bok.or.kr/api/#/)
