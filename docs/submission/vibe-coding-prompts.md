# 바이브코딩 지시 (AI 도구에게 준 실제 프롬프트)

> 과제전형 제출물 ⑤ · 지원자: 윤동혁 · 포지션: AI 애플리케이션 엔지니어
>
> 본 문서는 이 저장소를 개발하면서 **Claude Code (Opus 4.7)** 에게 준 바이브코딩 지시의 대표 4종을 추려 정리한 것입니다. 각 프롬프트는 과제 요건에 따라 **[역할 · 기능 · UI/UX · 기술 스택]** 4개 요소를 모두 포함하도록 구성했습니다. AI 의 응답은 포함하지 않았습니다.

---

## 사용한 AI 도구

| 용도 | 도구 |
|---|---|
| 코드 생성 · 리팩터링 · 문서 작성 | **Claude Code (Opus 4.7)** · Anthropic 공식 CLI |
| 런타임 LLM (feature 추출 · 리포트 요약) | **Groq `llama-3.3-70b-versatile`** (OpenAI API 호환) |
| 임베딩 (의미 유사도) | **sentence-transformers `all-MiniLM-L6-v2`** (로컬 384d) |
| 벡터 저장 · 검색 | **pgvector** (PostgreSQL 16 확장) |

---

## Prompt 1 — 초기 스캐폴딩 (백엔드 · 파이프라인)

**역할**: 백엔드 아키텍트 (데이터 파이프라인 + ML 서빙 경험자).

**기능**: Steam / App Store / itch.io 에서 게임 메타 + 리뷰를 수집하고, 4축(semantic · genre · tier · BM) 연속값 유사도를 계산해 "내 게임"의 경쟁작 Top N 을 **주간 배치** 로 생성·저장한다. 결과는 PM 이 소비할 수 있도록 DB 에 스냅샷 형태로 쌓는다.

**UI/UX**: CLI 중심. `gca <command>` 형태의 15개 서브커맨드. 표준출력에 stage 별 진행 상황을 출력하되, 상세 로그는 `pipeline_runs` 테이블에 기록한다.

**기술 스택**:

- 언어/런타임: Python 3.11+
- DB: PostgreSQL 16 + pgvector 확장 (로컬은 Docker, 프로덕션은 Supabase)
- LLM: Groq `llama-3.3-70b-versatile` (OpenAI SDK 호환)
- 임베딩: sentence-transformers `all-MiniLM-L6-v2` (완전 로컬, 384d)
- 캐시: `llm_cache`, `embedding_cache` 테이블 (SHA256 키) — 비용 제어용
- 서빙: FastAPI + uvicorn (read-only + POST /feedback, POST /games/my)

**산출물**:

1. **schema.sql** — 13개 테이블 (raw_games, raw_reviews, games, game_features(SCD Type 2), game_embeddings, game_similarities_weekly, pm_feedback, llm_cache, embedding_cache, pipeline_runs, weekly_reports, weight_history, weak_similarities)
2. **src/gca/collectors/** — Steam Store/Reviews API · App Store/itch stub
3. **src/gca/pipeline/** — normalize → feature_extractor(LLM) → embedder
4. **src/gca/engine/** — similarity · weak_labels · weight_tuner (NDCG@k grid search)
5. **src/gca/report/weekly.py** — Jinja2 템플릿 + Groq 요약으로 Markdown 리포트
6. **src/gca/cli.py** — 15개 서브커맨드 (collect:steam, normalize, extract-features, embed, similarity --week, report --week, tune-weights, add-my-game, …)

---

## Prompt 2 — 프런트엔드 3 페이지

**역할**: 프런트엔드 엔지니어 (App Router + Server Components 중급 이상).

**기능**:
1. **내 게임 관리** — Steam AppID 등록 → is_my_game 플래그 → 카드 그리드 조회
2. **경쟁작 분석** — 선택한 내 게임에 대한 Top 10 경쟁작 표시 + 👍/👎 피드백 수집
3. **주간 리포트 소비** — Markdown 리포트 렌더링 + PDF 저장

**UI/UX**:

- 라우트 3개:
  - `/` — My Games 카드 그리드 + `AddMyGameForm` (Steam appid input + submit)
  - `/games/[id]` — 경쟁작 테이블 (순위 · 게임명 · 종합 점수 · **4축 component score bar** · upvote/downvote · 스토어 링크). 우상단에 "Weekly Report" CTA.
  - `/games/[id]/report` — Markdown 리포트 본문 + 우상단 고정 "Download PDF" 버튼
- 톤: Tailwind **zinc 모노톤**, 중성 인디고 포인트. 카드·테이블은 정보 밀도 우선.
- 서버 컴포넌트를 기본으로 하고, 이벤트가 필요한 컴포넌트만 `"use client"`.
- 접근성: 주요 인터랙션 영역은 키보드 포커스 가능해야 함.

**기술 스택**:

- Next.js 16 (App Router) · React 19 · TypeScript
- Tailwind CSS v4 (PostCSS 파이프라인) · turbopack dev
- 데이터 페치: `fetch` + `NEXT_PUBLIC_API_BASE_URL` (Vercel env)
- 상태: React Server Components 우선 · 필요한 경우 useState/useTransition
- react-markdown 10.x + remark-gfm 4.x (Prompt 4 참조)

---

## Prompt 3 — Terraform IaC (Vercel + Supabase)

**역할**: DevOps / 플랫폼 엔지니어 (Terraform + 서드파티 프로바이더 경험).

**기능**: 이 저장소의 프로토타입을 **`terraform apply` 1회** 로 공개 URL 에 배포할 수 있게 IaC 를 작성한다. Vercel 에 web/api 프로젝트 2개, Supabase 에 Postgres 프로젝트 1개를 생성하고, 스키마를 자동 적용하며, 환경 변수를 자동 주입한다.

**UI/UX**: 해당 없음 (개발자 대상 CLI 경험 — `terraform init && terraform apply` 로 끝).

**기술 스택**:

- Terraform `>=1.5`
- Provider: `vercel/vercel ~> 2.0`, `supabase/supabase ~> 1.5`, `hashicorp/null ~> 3.2`
- 모듈 구조: `infra/terraform/modules/{vercel,supabase}` · 루트에서 조합
- 스키마 적용: `null_resource` + `local-exec` (bash 인터프리터) → `psql` 로 `schema.sql` 실행
- 환경 변수 자동 주입:
  - API 프로젝트: `DATABASE_URL`, `GROQ_API_KEY`, `LLM_MODEL`
  - Web 프로젝트: `NEXT_PUBLIC_API_BASE_URL` (= API 프로젝트의 `*.vercel.app` URL)
- 민감 변수: `sensitive = true` 로 마킹

**산출물**:

- `infra/terraform/main.tf` (루트)
- `infra/terraform/variables.tf`
- `infra/terraform/terraform.tfvars.example` (토큰 템플릿)
- `infra/terraform/modules/supabase/` (`main.tf`, `variables.tf`, `outputs.tf`)
- `infra/terraform/modules/vercel/` (`main.tf`, `variables.tf`)

---

## Prompt 4 — 주간 리포트 페이지 + PDF 저장

**역할**: 프런트엔드 엔지니어.

**기능**: `/games/[id]/report` 라우트 신설. API 의 `GET /games/{id}/report/markdown` 로부터 Markdown 을 받아 렌더링하고, 브라우저 인쇄 기능으로 **PDF 로 저장** 가능하게 한다.

**UI/UX**:

- 서버 컴포넌트(`page.tsx`) 가 `api.getReportMarkdown(baseGameId)` 로 데이터 페치 → 클라이언트 컴포넌트 `ReportView` 에 넘김.
- `ReportView` 는 react-markdown + remark-gfm 으로 렌더링하며, 각 MD 요소(h1/h2/h3/p/ul/ol/table/code…) 에 Tailwind prose 에 맞춘 커스텀 컴포넌트를 주입.
- **우상단 고정 "Download PDF" 버튼** — `window.print()` 호출.
- `@media print` 스타일로:
  - 네비·헤더·Download 버튼 숨김
  - `prose` 타이포그래피는 유지
  - 배경색 제거, 여백 조정
- 로딩/에러 상태는 보이지 않도록 서버 컴포넌트에서 try/catch 후 404 처리.

**기술 스택**:

- Next.js 16 App Router · React 19 (클라이언트 컴포넌트: `"use client"`)
- react-markdown `^10.1.0` + remark-gfm `^4.0.1`
- Tailwind CSS v4 · `@tailwindcss/typography` prose 유틸리티
- 인쇄: 네이티브 `window.print()` (외부 라이브러리 불필요)

**산출물**:

- `web/app/games/[id]/report/page.tsx` (서버 컴포넌트 · 데이터 페치)
- `web/app/games/[id]/report/ReportView.tsx` (클라이언트 컴포넌트 · 렌더)
- `web/app/games/[id]/report/print.css` (또는 `@media print` 블록)
- `web/lib/api.ts` 에 `getReportMarkdown(baseGameId)` 추가

---

## 프롬프트 설계 원칙 (공통)

이 네 프롬프트에 공통적으로 적용한 설계 원칙:

1. **[역할 · 기능 · UI/UX · 기술 스택] 4요소를 모두 명시** — 역할은 페르소나를 한정해 톤을 맞추고, 기능은 수용 기준을 명확히 하며, UI/UX 는 의사결정이 필요한 세부를 선제 고정하고, 기술 스택은 호환성/의존성 선택 폭을 좁힘.
2. **산출물 목록을 가능한 한 구체적으로** — 파일 경로까지 미리 지시하면 AI 가 일관된 저장소 구조를 유지.
3. **비기능 요구(캐시 · 관측성 · 접근성) 를 프롬프트에 포함** — 나중에 덧붙이기보다 처음부터 설계에 포함시키는 것이 손이 덜 감.
4. **결정을 미루는 표현(예: "적절히", "보통") 금지** — "Tailwind zinc 모노톤" 처럼 **실제 값** 으로 고정. AI 의 기본값에 의존하지 않음.

---

## 저장소 전체와의 관계

| 프롬프트 | 저장소 내 결과물 |
|---|---|
| ① 초기 스캐폴딩 | `schema.sql`, `src/gca/**`, 13개 테이블 + CLI 15개 서브커맨드 |
| ② FE 3 페이지 | `web/app/page.tsx`, `web/app/games/[id]/page.tsx`, `web/components/**` |
| ③ Terraform IaC | `infra/terraform/**` |
| ④ 리포트 페이지 | `web/app/games/[id]/report/**` |

각 결과물은 실제로 동작하는 상태이며, 본 과제의 "프로토타입 링크" 에서 확인 가능합니다.
