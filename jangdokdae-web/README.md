# 장독대 Web MVP

하루에 꼭 볼 세 가지 이슈만 읽고, 이슈마다 한 문제를 풀면 학습이 끝나는 Next.js 앱입니다.

## 사용자 흐름

1. 관심 섹터를 1~3개 고릅니다.
2. `내 관심 → 시장 맥락 → 시야 넓히기` 순서의 최대 세 이슈를 받습니다.
3. 각 이슈의 해설, 용어, 원문 출처를 읽습니다.
4. 이슈마다 핵심 퀴즈 한 문제를 제출합니다.
5. 세 문제를 제출하면 오늘의 학습이 완료됩니다.

로그인 없이 먼저 사용할 수 있는 MVP입니다. 관심사와 당일 진행 상태는 브라우저
`localStorage`에 저장됩니다. FastAPI는 로그인 쿠키가 있으면 DB에도 완료 상태를 기록합니다.

## 로컬 실행

먼저 `jangdokdae-server`에서 FastAPI를 8000번 포트로 실행합니다.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

`.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

브라우저에서 <http://localhost:3000>을 엽니다.

## 검사

```bash
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

E2E 테스트는 로컬의 Next.js와 FastAPI, 그리고 FastAPI `.env`가 가리키는 DB를 사용합니다.
테스트는 관심사 선택부터 세 이슈의 퀴즈와 `3/3` 완료까지 확인합니다.

## 운영 배포 시 필요한 설정

프론트 호스팅의 환경변수에 아래 값을 등록하고 다시 빌드합니다.

```env
NEXT_PUBLIC_API_BASE_URL=https://배포한-FastAPI-주소
```

FastAPI 운영 환경에는 최소한 다음 값이 필요합니다.

```env
DATABASE_URL=Neon-pooled-주소
SECRET_KEY=운영용-비밀값
CORS_ORIGINS=https://배포한-프론트-도메인
FRONTEND_BASE_URL=https://배포한-프론트-도메인
COOKIE_SECURE=true
```

프론트와 API가 서로 다른 최상위 도메인이고 로그인을 활성화한다면 쿠키 정책을 별도로
검토해야 합니다. 현재 MVP의 게스트 학습 흐름은 쿠키 없이 동작합니다.

## 오늘의 계획 고정 규칙

한국 시간 날짜와 관심사 조합별로 첫 API 응답을 브라우저에 저장합니다. 따라서 오후
파이프라인이 새 콘텐츠를 생성해도 이미 학습을 시작한 사용자의 세 이슈가 당일 중간에
바뀌지 않습니다. 다음 날 또는 관심사 변경 시 새 계획을 받습니다.
