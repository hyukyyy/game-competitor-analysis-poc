# 바이브코딩 지시 내용 (AI 응답 제외)

> 과제전형 제출물 · 지원자: 윤동혁 · 포지션: AI 애플리케이션 엔지니어
>
> 본 문서는 이 저장소를 개발하면서 **Claude Code (Opus 4)** 에게 준 바이브코딩 지시를 실제 대화 흐름 순서대로 정리한 것입니다.
> 각 Phase 별로 **실제 프롬프트 원문 → 의사결정 맥락 → 기술적 피봇**을 기록했습니다.
> AI 의 응답은 포함하지 않았습니다.

---

## 사용한 AI 도구

| 용도 | 도구 |
|---|---|
| 코드 생성 · 리팩터링 · 문서 작성 | **Claude Code (Opus 4)** · Anthropic 공식 CLI |
| 런타임 LLM (feature 추출 · 리포트 요약) | **Groq `llama-3.3-70b-versatile`** (OpenAI API 호환) |
| 임베딩 (의미 유사도) | **sentence-transformers `all-MiniLM-L6-v2`** (로컬 384d) |
| 벡터 저장 · 검색 | **pgvector** (PostgreSQL 16 확장) |

---

## Phase 1 — 설계 논의 (세션 1, 프롬프트 13회)

### 1-1. 초기 설계서 전달

AI에게 전달한 최초 입력은 13개 섹션으로 구성된 **구현 설계서** 전문입니다:

> **프롬프트 원문 (요약)**:
>
> ```
> 게임 경쟁작 자동 분석 시스템 – 구현 설계서 (Prototype)
>
> 1. 프로젝트 개요
>    - 목적: 경쟁작 탐색 및 리포트 생성 업무 효율화
>    - 범위: 모바일 + PC (Play Store / Steam), Top 200개, 주간 배치
>
> 2. 시스템 전체 구조
>    Batch Server → Raw Data DB → Normalized DB → Analysis Server (LLM)
>    → Feature Store → Similarity Engine → Result DB → API Server → Frontend
>
> 3~4. 데이터 레이어 설계
>    - raw_games (원본 보존)
>    - games (정규화)
>    - game_features (LLM 분석 결과: genre, subgenre, bm, play_style, session_length, core_loop)
>    - game_similarities (유사도 결과 캐싱)
>
> 5. 데이터 파이프라인: 수집 → 정제 → Feature 추출(LLM) → 유사도 계산 → 결과 저장
>
> 6. 유사도 계산식 (초안):
>    score = genre_match * 0.4 + bm_match * 0.2 + play_style_similarity * 0.2
>            + session_length_match * 0.1 + 기타 * 0.1
>
> 7. Human-in-the-loop: Top N 결과 검수, 검토 대상 ≤ 20
>
> 8. 성능 최적화: 동일 장르만 비교, Top 후보군 제한, Feature 캐싱
>
> 9. 개발 일정: 4주 (Week 1 DB/크롤링, Week 2 Feature/파이프라인,
>    Week 3 유사도/저장, Week 4 리포트/튜닝)
>
> 이거 분석해봐
> ```

### 1-2. 핵심 설계 피봇 (4회 반복 대화)

초기 설계서를 AI와 논의하면서 아래 결정들을 순차적으로 내렸습니다:

> **프롬프트 원문**:
>
> ```
> 1. 동일장르 아니어도 포함
> 2. 기타는 제거
> 3. 연속성 기반으로 쓰자 그럼
> ```

**의사결정 맥락**: 초기 설계의 "동일 장르만 비교" + "기타 카테고리" 접근은 경쟁작을 놓칠 위험이 있음. 장르가 다르더라도 target user가 겹칠 수 있으므로, 이진 매칭(같다/다르다) 대신 **연속값 유사도**로 전환.

> **프롬프트 원문**:
>
> ```
> 게임 서비스에서 경쟁작을 정의하는 기준을 어떻게 정해야될까?
> 아니 게임을 만들고 있는게 아니라 게임 회사의 내부 업무 프로세스를 개선하는 관점으로 보는거야.
> 게임 회사에서는 지속적으로 경쟁작을 선정하고 분석해야 되는데 결국 이것도 반복 업무잖아?
> 주기적으로 찾아야 하니까.
> 근데 이 부분을 자동화하려면 어쨌든 경쟁작이라는걸 정의부터 해야할 것 같아서
>
> Step 1: 게임을 Feature로 분해
> - 이 정보들을 google store 나 steam 같은 게임 플랫폼에서 가져올 수가 있어?
> - 자동화하려면 api 를 제공해줘야 되잖아
> - 안된다면 ai 활용해서 간접 측정할 방법이라도 있나
>
> Step 2: 유사도 계산 모델 만들기
> - 이 계산 모델이라는 것도 내가 보기엔 가중치가 하나의 최적해로 고정되는게 아니라
>   그때 그때 adaptive 하게 바뀔 것 같은데
>   그럼 최종적으로 그 계산이 맞다 라는 점수를 측정하기 위한 최종 기준이 필요하잖아
> - 그건 어느 값으로 하면 되지 결국 target user 층이 겹치는 정도로 보면 되나
> ```

**의사결정 맥락**:
- **경쟁작 정의** = target user 층 겹침 → 직접 측정 불가 → 4가지 축(semantic, genre, tier, BM)의 연속값 유사도로 근사
- **가중치 적응** = 고정 가중치가 아니라 PM 피드백 기반으로 자동 재튜닝 → NDCG@k 기준 grid search
- **데이터 소스** = 플랫폼 API에서 직접 가져오되, 구조화된 feature는 LLM으로 간접 추출

> **프롬프트 원문**:
>
> ```
> PM/분석가가:
>   잘못 잡힌 경쟁작 제거
>   중요한 경쟁작 수동 추가
> - 이걸 할거면 그냥 일 2번 하는거잖아
>
> 시장 리서치 자동화 (리포트용)
> - 아무래도 이거지 우선은?
> 이거 실제 프로토타입으로 만들게 개발 기획 짜봐
> ```

**의사결정 맥락**: Human-in-the-Loop "검수·승인" 플로우는 PM에게 업무를 2번 시키는 것과 같음. 대신 **👍/👎 implicit feedback**만 수집하고 시스템이 알아서 학습하는 구조로 전환.

> **프롬프트 원문**:
>
> ```
> 내부 툴로 사용 목적이니까 각 서버의 역할은 내가 그리는 그림으론
> - batch server (serverless batch function) : 경쟁작 데이터 batch search 및 insert
> - analysis server : python ml 로 새로운 데이터에 대한 분석 batch 실행
> - api-server : fe 에서 data 조회에만 사용
> - fe : 결과 정리 페이지
> 이렇게 되면 되지 않을까?
> ```

**의사결정 맥락**: 서버 역할을 단순하게 4개로 정리. 실제 구현에서는 batch + analysis를 하나의 CLI(`gca`)로 통합, api-server는 FastAPI, fe는 Next.js로 구현.

---

## Phase 2 — 백엔드 구현 (세션 2, 프롬프트 30+회)

### 2-1. 환경 설정 + 데이터 수집

> **프롬프트 원문**:
>
> ```
> @docs/plan.md @docs/plan-status.md 점검해봐
> ```
>
> ```
> 이전 세션에서 다른 환경에서 작업하느라 docker / python 없어서
> week1 에 진행해야 되는 db 설정을 못했거든? 지금 실행되는지 확인해봐
> ```

**맥락**: 세션 1에서는 Windows 환경이라 Docker/Python이 없어서 설계만 진행. 세션 2에서 Linux 환경으로 옮긴 뒤 실제 구현 시작.

### 2-2. 기술 스택 피봇 — 임베딩

> **프롬프트 원문**:
>
> ```
> anthropic 이랑 openai 가 둘다 필요한거야?
> ```
>
> ```
> - Anthropic만: feature 추출은 Claude 유지 + 임베딩을 로컬 모델(sentence-transformers)로 변경
>   → embedder.py 수정 필요
> 일단 이렇게 가자 poc 단계 치고 과한거 같네
> ```

**기술적 피봇**: 초기 계획은 OpenAI Embedding API 사용이었으나, PoC 단계에서 유료 API 2개(Anthropic + OpenAI)를 모두 쓰는 것은 과도함. **sentence-transformers `all-MiniLM-L6-v2`를 로컬로 실행**하는 것으로 전환. 384차원이지만 PoC 수준에서는 충분하고, 운영비 $0 달성에 기여.

### 2-3. 기술 스택 피봇 — LLM

**기술적 피봇**: Feature 추출용 LLM을 처음에는 Claude API로 시도했으나 인증 이슈로 전환 결정. **Groq 무료 tier (`llama-3.3-70b-versatile`)로 전환**. OpenAI SDK 호환이라 코드 변경 최소화하면서 무료 tier로 PoC 운영비 $0 달성.

### 2-4. 멀티 플랫폼 수집 확장

Steam 수집(200개 게임 + 리뷰) 완료 후, App Store · itch.io 수집기를 추가 구현하도록 지시. App Store는 비공식 경로(`app-store-scraper`)로 메타 + 리뷰 수집, itch.io는 웹 스크래핑 방식.

### 2-5. 파이프라인 완성 및 비용 구조 확인

각 파이프라인 단계(collect → normalize → extract-features → embed → similarity → report)가 CLI 서브커맨드로 독립 실행 가능한지 확인. Feature 추출은 LLM 호출 비용이 있지만 `llm_cache` 테이블로 동일 입력 재호출 방지 — 사실상 일회성 비용이며, 이후 주간 배치에서는 변경된 게임만 재분석하도록 `--changed-only` 옵션 적용.

---

## Phase 3 — 프론트엔드 + 배포 (세션 3~4)

### 3-1. 프론트엔드 3페이지

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

**기술 스택**:

- Next.js 16 (App Router) · React 19 · TypeScript
- Tailwind CSS v4 (PostCSS 파이프라인) · turbopack dev
- 데이터 페치: `fetch` + `NEXT_PUBLIC_API_BASE_URL` (Vercel env)
- react-markdown 10.x + remark-gfm 4.x (리포트 렌더링)
- 인쇄: 네이티브 `window.print()` + `@media print` 스타일

**산출물**:

- `web/app/page.tsx` — 홈 (My Games 그리드 + 게임 등록 폼)
- `web/app/games/[id]/page.tsx` — 경쟁작 분석 (Top 10 테이블 + 피드백)
- `web/app/games/[id]/report/page.tsx` — 주간 리포트 (마크다운 렌더링 + PDF)
- `web/app/games/[id]/report/ReportView.tsx` — 클라이언트 컴포넌트 (react-markdown)
- `web/lib/api.ts` — API 래퍼 함수
- `web/app/AddMyGameForm.tsx` — 게임 등록 폼 (클라이언트 컴포넌트)

### 3-2. Terraform IaC

**역할**: DevOps / 플랫폼 엔지니어.

**기능**: `terraform apply` 1회로 공개 URL에 배포. Vercel에 web/api 프로젝트 2개, Supabase에 Postgres 프로젝트 1개 생성, 스키마 자동 적용, 환경 변수 자동 주입.

**기술 스택**:

- Terraform `>=1.5`
- Provider: `vercel/vercel ~> 2.0`, `supabase/supabase ~> 1.5`, `hashicorp/null ~> 3.2`
- 모듈 구조: `infra/terraform/modules/{vercel,supabase}` · 루트에서 조합
- 스키마 적용: `null_resource` + `local-exec` → `psql` 로 `schema.sql` 실행
- 환경 변수 자동 주입:
  - API: `DATABASE_URL`, `GROQ_API_KEY`, `LLM_MODEL`
  - Web: `NEXT_PUBLIC_API_BASE_URL` (= API 프로젝트의 `*.vercel.app` URL)

**산출물**:

- `infra/terraform/main.tf`, `variables.tf`, `terraform.tfvars.example`
- `infra/terraform/modules/supabase/` (main, variables, outputs)
- `infra/terraform/modules/vercel/` (main, variables)

---

## 기술적 피봇 요약

개발 과정에서 발생한 주요 기술 전환을 정리합니다:

| 시점 | 원래 계획 | 전환 결과 | 이유 |
|---|---|---|---|
| 유사도 모델 | 이진 매칭 (genre_match * 0.4) | 4축 연속값 유사도 (cosine, KL divergence) | "동일 장르가 아니어도 경쟁작" — 연속값이 더 정확 |
| 검수 방식 | Human-in-the-Loop (검수·승인) | implicit feedback (👍/👎만) | "일 2번 하는 것" — PM 부담 최소화 |
| 임베딩 API | OpenAI Embedding API | sentence-transformers 로컬 (384d) | PoC에 유료 API 2개는 과도, 운영비 $0 목표 |
| LLM API | Claude API (Anthropic) | Groq llama-3.3-70b-versatile | 인증/결제 이슈 + 무료 tier 활용, OpenAI SDK 호환 |
| Feature 정의 | 6개 카테고리 이진값 | LLM 추출 연속값 + SCD Type 2 이력 | "기타 제거" + 시간에 따른 변화 추적 필요 |

---

## 프롬프트 설계 원칙 (공통)

1. **구현 설계서를 먼저 작성해서 전달** — 빈 프롬프트가 아닌, 데이터 레이어·아키텍처·계산식까지 포함한 13개 섹션 설계서를 초기 입력으로 사용. AI가 구조를 잡는 게 아니라 사람이 잡은 구조를 AI가 구현.
2. **반복적 의사결정** — 한 번에 완성된 프롬프트를 주는 게 아니라, AI의 분석을 보고 "이건 아니다"/"이걸로 가자"를 반복. 특히 경쟁작 정의(이진→연속), 검수 방식(HITL→implicit), LLM 선택(Claude→Groq) 등은 모두 대화 중 피봇.
3. **기술 스택 피봇을 두려워하지 않음** — 안 되면 바로 대안으로 전환 (Claude API 인증 실패 → Groq, OpenAI 임베딩 → 로컬). PoC의 목적은 "동작하는 End-to-End"이므로 특정 기술에 집착하지 않음.
4. **비기능 요구를 초기부터 포함** — 캐시(`llm_cache`, `embedding_cache`), 관측성(`pipeline_runs`), 이력 관리(`weight_history`, SCD Type 2) 등을 나중이 아닌 설계 단계에서 프롬프트에 명시.
5. **결정을 미루는 표현 금지** — "적절히", "보통" 대신 구체적 값("Tailwind zinc 모노톤", "384d", "NDCG@k")으로 고정. AI의 기본값에 의존하지 않음.

---

## 저장소 전체와의 관계

| Phase | 저장소 내 결과물 |
|---|---|
| ① 설계 논의 | `docs/plan.md`, `docs/conversation.md` (프롬프트 원문 보존) |
| ② 백엔드 구현 | `schema.sql` (13개 테이블), `src/gca/**` (collectors, pipeline, engine, report, api, cli) |
| ③-1 FE 3페이지 | `web/app/page.tsx`, `web/app/games/[id]/page.tsx`, `web/app/games/[id]/report/` |
| ③-2 Terraform IaC | `infra/terraform/**` (modules/vercel, modules/supabase) |

각 결과물은 실제로 동작하는 상태이며, 본 과제의 "프로토타입 링크"에서 확인 가능합니다.
