# 서비스 아키텍처

> 작성일: 2026-04-18 · 기준: commit `5e6370f` · 이 문서는 현재 구현 상태의 single source of truth 입니다.

## 한 줄 요약

게임 리서치팀의 **주간 경쟁작 리포트 작성을 자동화**하는 내부 PM 툴.
PM이 `is_my_game` 으로 지정한 게임을 base 로 삼아, 4축 연속값 유사도로 Top N 경쟁작을 계산하고 주간 리포트로 제공한다.

주요 컴포넌트 5개:

1. **Collectors** — Steam / App Store / itch.io 메타+리뷰 수집
2. **Pipeline** — 정규화 + LLM feature 추출 + 임베딩 (sentence-transformers 로컬)
3. **Engine** — 유사도 계산 · 가중치 튜닝 · weak label 수집
4. **Report + API** — Jinja2 주간 리포트 생성 · FastAPI read-only 엔드포인트
5. **FE (Next.js 16)** — 내 게임 / 경쟁작 / 리포트 3페이지 · upvote/downvote

---

## 배포 토폴로지

### 로컬 개발 모드

```
┌────────────────────────────┐
│  dev machine (Windows/WSL) │
│                            │
│  .venv ── gca CLI (배치)   │────┐
│  .venv ── gca serve :8000  │──┐ │
│                            │  │ │
│  web/ ── next dev :3000    │──┼─┼──── HTTP → API :8000
└────────────────────────────┘  │ │
                                │ ▼
                        ┌───────┴──────────────┐
                        │ Docker: gca-pg       │
                        │ pgvector/pgvector:pg16│
                        │ host:55432 → ctr:5432 │
                        └──────────────────────┘

필수 env:
  DATABASE_URL  = postgresql://postgres:...@localhost:55432/postgres
  GROQ_API_KEY  = gsk_...
  NEXT_PUBLIC_API_BASE_URL = http://localhost:8000   (web/.env.local)
```

### 프로덕션 모드 (Terraform)

```
          GitHub repo (main branch)
            │
            ├── push → Vercel build
            │     ┌──────────────────────┐
            │     │ Vercel "gca-web"     │   NEXT_PUBLIC_API_BASE_URL=
            │     │ root=web/, next@16   │     https://gca-api.vercel.app
            │     │ https://gca-web...   │
            │     └──────────┬───────────┘
            │                │ fetch
            │     ┌──────────▼───────────┐
            │     │ Vercel "gca-api"     │   DATABASE_URL, GROQ_API_KEY, LLM_MODEL
            │     │ root=/, @vercel/python│
            │     │ api/index.py → ASGI  │
            │     └──────────┬───────────┘
            │                │ psycopg (SSL)
            └─────────▼──────▼───────────┐
                      Supabase project    │
                      Postgres 15 +       │
                      pgvector extension  │
                      schema.sql 적용     │
                      (null_resource)     │
                      └───────────────────┘

배치 파이프라인 (ML deps 포함):
  로컬 또는 CI runner 에서 gca CLI 실행 → Supabase DB write
  Vercel serverless 에서는 실행 불가 (sentence-transformers > 50MB 제한)
```

---

## 5 레이어 아키텍처 (데이터 흐름)

```
[Cron / 수동 실행]
        │
        ▼
┌────────────────┐
│ 1. Collectors  │  steam.py · appstore.py · itch.py · playstore.py(stub)
└────────┬───────┘
         ▼ raw_games · raw_reviews
┌────────────────┐
│ 2. Pipeline    │  normalize → feature_extractor (Groq) → embedder (local 384d)
└────────┬───────┘
         ▼ games · game_features (SCD Type 2) · game_embeddings · llm_cache · embedding_cache
┌────────────────┐
│ 3. Engine      │  weak_labels → weight_tuner → similarity (is_my_game 필터)
└────────┬───────┘
         ▼ weak_similarities · weight_history · game_similarities_weekly
┌────────────────┐
│ 4. Report      │  weekly.py (Jinja2 템플릿 + Groq summary)
└────────┬───────┘
         ▼ weekly_reports
┌────────────────┐
│ 5. API + FE    │  FastAPI (read-only) · Next.js 16 (3 pages)
└────────┬───────┘
         ▼ pm_feedback (유일한 write)
         └─→ 다음 주 weight_tuner 입력
```

### 레이어별 테이블 소유권

| Layer | Writes | Reads |
|---|---|---|
| Collectors ([src/gca/collectors/](../src/gca/collectors/)) | `raw_games`, `raw_reviews` | — |
| Pipeline / normalize ([src/gca/pipeline/normalize.py](../src/gca/pipeline/normalize.py)) | `games` | `raw_games` |
| Pipeline / feature_extractor ([src/gca/pipeline/feature_extractor.py](../src/gca/pipeline/feature_extractor.py)) | `game_features`, `llm_cache` | `games`, `raw_reviews` |
| Pipeline / embedder ([src/gca/pipeline/embedder.py](../src/gca/pipeline/embedder.py)) | `game_embeddings`, `embedding_cache` | `games`, `raw_reviews` |
| Engine / similarity ([src/gca/engine/similarity.py](../src/gca/engine/similarity.py)) | `game_similarities_weekly` | features, embeddings, weights, `games.is_my_game` |
| Engine / weight_tuner ([src/gca/engine/weight_tuner.py](../src/gca/engine/weight_tuner.py)) | `weight_history` | `pm_feedback`, `weak_similarities` |
| Engine / weak_labels ([src/gca/engine/weak_labels.py](../src/gca/engine/weak_labels.py)) | `weak_similarities` | `games`, `game_features` |
| Report ([src/gca/report/weekly.py](../src/gca/report/weekly.py)) | `weekly_reports` | similarities, games, `games.is_my_game` |
| API / CLI add-my-game ([src/gca/cli.py](../src/gca/cli.py)) | `games.is_my_game`, `raw_games` | — |
| API / feedback ([src/gca/api/routes/feedback.py](../src/gca/api/routes/feedback.py)) | `pm_feedback` | `games` |
| API read-only ([src/gca/api/routes/competitors.py](../src/gca/api/routes/competitors.py), [reports.py](../src/gca/api/routes/reports.py)) | — | 전체 read |
| 공통 ([src/gca/pipeline/runs.py](../src/gca/pipeline/runs.py)) | `pipeline_runs` | — |

---

## 배치 vs 라이브 경로

### 배치 (주 1회, 로컬 또는 CI)

```
gca collect:steam --fetch-reviews   # raw_games, raw_reviews
gca normalize                       # → games
gca extract-features --changed-only # → game_features (SCD Type 2)
gca embed --changed-only            # → game_embeddings (pgvector 384d)
gca weak-labels --source tag_overlap# → weak_similarities
gca tune-weights                    # → weight_history
gca similarity                      # → game_similarities_weekly (is_my_game base 만)
gca report                          # → weekly_reports
```

### 라이브 (PM 클릭)

```
 Browser → Next.js SSR
         → fetch(NEXT_PUBLIC_API_BASE_URL)
         → FastAPI (Vercel serverless)
         → Supabase Postgres (read-only)

엔드포인트:
  GET  /games?mine=true             → 내 게임 목록
  GET  /competitors?base_game_id=1  → Top N 경쟁작 + component_scores
  GET  /reports?base_game_id=1&format=markdown
  POST /feedback                    → pm_feedback (유일한 write)
```

`POST /reports/generate` 는 similarity → embedder 체인을 트리거 → sentence-transformers 필요.
Vercel 에서는 동작하지 않으며 배치 경로에서만 사용.

---

## DB 스키마 (13 테이블)

전체 DDL: [schema.sql](../schema.sql)

| # | 테이블 | 설명 |
|---|---|---|
| 1 | `raw_games` | 플랫폼 원본 payload (JSONB) 보존. `(platform, external_id, collected_at)` 유니크 |
| 2 | `raw_reviews` | 리뷰 원본 (text, rating, posted_at) |
| 3 | `games` | 정규화된 게임. **`is_my_game BOOLEAN`** + partial index `idx_games_my` |
| 4 | `game_features` | LLM 추출 feature. **SCD Type 2** (`valid_from`/`valid_to=NULL` = 현재) |
| 5 | `game_embeddings` | **pgvector vector(384)** — `all-MiniLM-L6-v2` 출력 |
| 6 | `game_similarities_weekly` | 주간 유사도 스냅샷 + `component_scores` (explainability) |
| 7 | `pm_feedback` | upvote/downvote/clicked/added signal — 가중치 학습 입력 |
| 8 | `llm_cache` | SHA256(prompt) → JSONB 출력 — Groq 비용 절감 |
| 9 | `embedding_cache` | SHA256(text) → vector(384) |
| 10 | `pipeline_runs` | stage × week_of × status — 관측성 |
| 11 | `weekly_reports` | 생성된 리포트 (JSONB: top_n/new_entrants/rank_changes/updates_summary) |
| 12 | `weight_history` | 튜닝된 가중치 이력 + NDCG@10 |
| 13 | `weak_similarities` | 플랫폼 similar signal (`steam_morelike` / `tag_overlap`) |

### 핵심 설계 결정

- **SCD Type 2 (`game_features`)** — feature 변경 시 `valid_to = NOW()` 로 닫고 새 row 추가. 과거 시점 리포트 재현 가능.
- **pgvector vector(384)** — psycopg3 `register_vector(conn)` 으로 문자열 대신 list 로 받음 ([src/gca/db.py](../src/gca/db.py)).
- **`is_my_game` partial index** — PM 등록 게임만 인덱싱 (일반 목록은 풀스캔 허용, base 선택만 빠르게).
- **멱등성** — 모든 stage 가 `(platform, external_id, week_of)` 단위 UPSERT.

---

## 유사도 공식

구현: [src/gca/engine/similarity.py:58-86](../src/gca/engine/similarity.py#L58-L86)

```
score = 0.40 · semantic + 0.25 · genre + 0.20 · tier + 0.15 · bm
```

| 축 | 계산 방식 | 입력 |
|---|---|---|
| `semantic` | `cosine(desc_embed_a, desc_embed_b)` | `game_embeddings.description_embedding` (384d) |
| `genre` | `cosine(genre_embed_a, genre_embed_b)` | `game_features.genre` → on-the-fly 임베딩 (embedding_cache) |
| `tier` | `exp(-|tier_a - tier_b| / 0.3)` | `log1p(review_count)` 정규화 → [0,1] |
| `bm` | `1 - KL_sym(bm_dist_a, bm_dist_b) / (2·log 4)` | `game_features.bm_dist` = `{gacha, ads, premium, sub}` 확률분포 |

`component_scores` 는 `game_similarities_weekly.component_scores` JSONB 에 함께 저장 → FE 막대그래프로 설명가능성 확보.

가중치는 `gca tune-weights` 로 `pm_feedback` + `weak_similarities` 기반 grid search 에서 튜닝, `weight_history` 에 적재. 다음 `gca similarity` 실행 시 `load_latest_weights()` 로 자동 로드.

---

## 피드백 루프

```
┌──────────────────────┐
│ FE /games/[id]       │  PM 이 경쟁작 row 의 👍/👎 클릭
└──────────┬───────────┘
           │ POST /feedback { base, target, week_of, signal }
           ▼
┌──────────────────────┐
│ pm_feedback 테이블    │
└──────────┬───────────┘
           │ 주간 배치 (gca tune-weights)
           ▼
┌──────────────────────┐
│ weight_tuner         │  NDCG@k grid search
│ (pm + weak label)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ weight_history       │  weeks_of, weights JSONB, ndcg_score
└──────────┬───────────┘
           │ gca similarity 가 load_latest_weights()
           ▼
 다음 주 유사도 계산에 반영 → 리포트 품질 개선
```

검수 단계는 없음 — **upvote/downvote = 암묵적 signal 만**. PM 워크플로우에 추가 업무 없음.

---

## 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.11+ | batch + API |
| DB | PostgreSQL 16 + pgvector 0.8 | 로컬 Docker, 프로덕션 Supabase |
| LLM (feature / report summary) | Groq `llama-3.3-70b-versatile` | OpenAI-compatible API, 무료 tier |
| 임베딩 | sentence-transformers `all-MiniLM-L6-v2` (384d, 로컬) | 완전 로컬 — API 호출 없음 |
| Python HTTP | httpx + tenacity | retry/backoff |
| 템플릿 | Jinja2 | [src/gca/report/templates/weekly.md.j2](../src/gca/report/templates/weekly.md.j2) |
| API | FastAPI + uvicorn | CORS 허용, read-only + `POST /feedback` |
| FE | Next.js 16.2 + React 19 + Tailwind v4 + turbopack | App Router, async `params`/`searchParams` |
| FE Markdown | react-markdown | 커스텀 component 매핑 (no typography plugin) |
| IaC | Terraform 1.6+ (supabase + vercel + null providers) | [infra/terraform/](../infra/terraform/) |
| Vercel Python runtime | `@vercel/python` | `api/index.py` = ASGI export, lean deps ([api/requirements.txt](../api/requirements.txt)) |

---

## 관련 문서

- [docs/product-guide.md](./product-guide.md) — PM·기획자용 사용 플로우
- [docs/cli-guide.md](./cli-guide.md) — 개발자용 CLI·배포 명령어 레퍼런스
- [docs/not-done.md](./not-done.md) — 남은 작업 · 해결된 블로커
- [docs/progress-2026-04-18.md](./progress-2026-04-18.md) — 최근 세션 변경 상세

### 과거 문서 (outdated — 히스토리용)

- [docs/plan.md](./plan.md) — 초기 기획 (Claude/OpenAI 가정)
- [docs/architecture.md](./architecture.md) — 초기 아키텍처 (is_my_game / FE / IaC 반영 전)
- [docs/implementation.md](./implementation.md) — 초기 구현 노트
