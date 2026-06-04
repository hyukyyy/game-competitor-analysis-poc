# 구현 상세 정리 (Implementation Deep Dive)

> 작성일: 2026-06-04 · 코드 기준으로 직접 작성한 전체 구현 구조 + 기능별 구현 방식 + 주요 기능 상세 문서.

---

## 1. 한 줄 요약

게임 PM의 **주간 경쟁작 리포트 작성을 자동화**하는 내부 도구.
PM이 `is_my_game`으로 등록한 게임을 base로, 멀티 플랫폼(Steam/App Store/itch.io)에서 수집한 상위 게임들과 **4축 가중 유사도**를 계산해 Top-N 경쟁작을 뽑고, 전주 대비 변화(신규 진입·순위 변동)를 포함한 주간 리포트를 생성한다. PM의 upvote/downvote 피드백은 NDCG 기반 **가중치 자동 튜닝**으로 되먹임된다.

---

## 2. 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.11+ (백엔드/파이프라인), TypeScript (FE) |
| DB | Postgres + **pgvector** (Supabase) |
| LLM | Groq API (`llama-3.3-70b-versatile`) — OpenAI SDK 호환 모드 (`base_url=https://api.groq.com/openai/v1`) |
| 임베딩 | `sentence-transformers` 로컬 모델 `all-MiniLM-L6-v2` (384차원) |
| API | FastAPI + uvicorn |
| FE | Next.js 16 (App Router) + React 19 + Tailwind 4 + react-markdown |
| 리포트 | Jinja2 마크다운 템플릿 |
| HTTP/재시도 | httpx + tenacity (exponential backoff, 3회) |
| 배포 | Vercel ×2 (API: Python serverless `icn1` / FE: Next.js), Supabase (Terraform 모듈) |
| 설정 | pydantic-settings (`.env` 로드) — `src/gca/config.py` |

---

## 3. 레포 구조

```
.
├── schema.sql                  # 전체 DB 스키마 (pgvector 포함, idempotent)
├── vercel.json                 # FastAPI를 Vercel Python serverless로 배포 (region: icn1)
├── api/index.py                # Vercel 진입점 — gca.api.server:app re-export (ML deps 제외)
├── api/requirements.txt        # serverless용 경량 의존성 (sentence-transformers 미포함)
├── pyproject.toml              # gca 패키지 + `gca` CLI 엔트리포인트
├── src/gca/
│   ├── cli.py                  # argparse 기반 CLI — 14개 서브커맨드 (파이프라인 오케스트레이션)
│   ├── config.py               # Settings (DATABASE_URL, GROQ_API_KEY, 모델명 등)
│   ├── db.py                   # psycopg3 단명 커넥션 context manager + dict_row + pgvector 등록
│   ├── models.py               # Pydantic DTO: RawGame / RawReview / NormalizedGame
│   ├── collectors/             # 플랫폼별 수집기 (Protocol 기반)
│   │   ├── base.py             #   Collector Protocol: top_game_ids / fetch_game / fetch_reviews
│   │   ├── steam.py            #   SteamSpy(top100) + appdetails + appreviews
│   │   ├── appstore.py         #   iTunes Search/Lookup/RSS reviews
│   │   ├── itch.py             #   top-rated browse JSON + public API
│   │   └── playstore.py        #   google-play-scraper (옵션 deps, seed 목록 기반 stub)
│   ├── pipeline/
│   │   ├── normalize.py        # raw_games → games 정규화 (플랫폼별 payload 매핑)
│   │   ├── feature_extractor.py# LLM 구조화 feature 추출 + SCD Type 2 upsert
│   │   ├── feature_prompt.py   # SYSTEM / USER_TEMPLATE (JSON 스키마 + canary 질문)
│   │   ├── embedder.py         # 설명/리뷰 임베딩 생성 (lazy 모델 로드)
│   │   ├── cache.py            # llm_cache / embedding_cache (sha256 해시 키)
│   │   └── runs.py             # pipeline_runs 기록 context manager (관측성)
│   ├── engine/
│   │   ├── similarity.py       # 4축 유사도 수식 + 주간 배치 계산
│   │   ├── weight_tuner.py     # NDCG@k 그리드서치 가중치 튜닝
│   │   ├── weak_labels.py      # Steam morelike / tag overlap / Play Store similar
│   │   └── features.py         # feature/embedding 조회 헬퍼 (as-of 시점 조회)
│   ├── report/
│   │   ├── weekly.py           # 리포트 데이터 빌드 + Jinja2 렌더 + DB 저장
│   │   └── templates/weekly.md.j2
│   └── api/
│       ├── server.py           # FastAPI 앱 + CORS + 라우터 등록
│       └── routes/             # competitors / feedback / reports
├── web/                        # Next.js 16 FE (별도 Vercel 프로젝트)
│   ├── lib/api.ts              # 타입드 API 클라이언트 (NEXT_PUBLIC_API_BASE_URL)
│   └── app/
│       ├── page.tsx            # My Games 목록 + 게임 등록 폼
│       ├── AddMyGameForm.tsx   # POST /games/my 클라이언트 폼
│       └── games/[id]/
│           ├── page.tsx        # 경쟁작 테이블 페이지 (SSR, force-dynamic)
│           ├── CompetitorsTable.tsx  # 컴포넌트 점수 바 + upvote/downvote
│           └── report/         # 주간 리포트 뷰 (markdown 렌더 + print-to-PDF)
├── infra/terraform/            # Supabase 프로비저닝 + apply_schema.py
├── tests/                      # pytest (normalize 단위 테스트)
└── docs/                       # 본 문서 포함 문서 모음
```

---

## 4. 배포 토폴로지

```
┌─ Vercel (web/) ────────────┐      ┌─ Vercel (루트 vercel.json) ──────────┐
│ Next.js 16 FE              │ ───▶ │ FastAPI (Python serverless, icn1)    │
│ NEXT_PUBLIC_API_BASE_URL   │ HTTP │ api/index.py → gca.api.server:app    │
└────────────────────────────┘      │ includeFiles: src/** (경량 deps만)   │
                                    └──────────────┬───────────────────────┘
                                                   │ psycopg
        로컬 dev machine                            ▼
        .venv ── gca CLI (주간 배치 수동/cron) ──▶ Supabase Postgres (+pgvector)
        .venv ── gca serve :8000 (로컬 API)        ▲ Terraform 모듈로 스키마 적용
```

핵심 분리: **무거운 ML 작업(임베딩·LLM·유사도 계산)은 전부 CLI 배치**에서 수행하고, Vercel serverless API는 **계산 결과를 읽기만** 한다 (`api/requirements.txt`에 sentence-transformers 없음). 유일한 쓰기 경로는 `POST /feedback`, `POST /games/my`, `POST /reports/generate`.

---

## 5. 데이터 모델 (`schema.sql`)

| 테이블 | 역할 | 핵심 설계 |
|--------|------|-----------|
| `raw_games` | 원본 payload 보존 (JSONB) | `UNIQUE(platform, external_id, collected_at)` — 시점별 스냅샷, 재처리 가능 |
| `raw_reviews` | 리뷰 원본 | `UNIQUE(platform, review_id)` 중복 방지 |
| `games` | 정규화 레이어 | `UNIQUE(platform, external_id)` upsert, `is_my_game` 플래그 (partial index) |
| `game_features` | LLM 추출 feature 저장소 | **SCD Type 2**: `valid_from`/`valid_to`(NULL=현재) + `feature_version` — 시점 조회 가능 |
| `game_embeddings` | `vector(384)` ×2 (description/review) | game_id PK, upsert |
| `game_similarities_weekly` | 주간 유사도 스냅샷 | PK `(week_of, base, target)` + `rank` + `component_scores` JSONB(설명가능성) |
| `pm_feedback` | PM 시그널 | upvote/downvote/clicked/added — 튜닝 라벨 원천 |
| `weak_similarities` | 약한 정답 라벨 | source: steam_morelike / tag_overlap / playstore_similar |
| `weight_history` | 튜닝된 가중치 이력 | weights JSONB + ndcg_score + label_count |
| `llm_cache` / `embedding_cache` | 비용 절감 캐시 | sha256 input hash PK, hit_count 추적 |
| `pipeline_runs` | 배치 관측성 | stage/status/rows_in/rows_out/error |
| `weekly_reports` | 리포트 JSONB 저장 | `UNIQUE(week_of, base_game_id)` upsert |

레이어링: **raw(원본 보존) → normalized(games) → feature/embedding(파생) → similarity(주간 산출) → report(소비)**. 모든 단계가 upsert/`ON CONFLICT` 기반이라 재실행에 안전(idempotent).

---

## 6. 파이프라인 전체 흐름

```
gca collect:steam / collect:appstore / collect:itch     (외부 API → raw_games, raw_reviews)
        ▼
gca normalize                                            (raw_games 최신본 → games upsert)
        ▼
gca extract-features [--changed-only]                    (Groq LLM → game_features SCD2)
gca embed            [--changed-only]                    (MiniLM → game_embeddings)
        ▼
gca weak-labels --source tag_overlap|steam               (weak_similarities 적재)
gca tune-weights                                         (NDCG 그리드서치 → weight_history)
        ▼
gca similarity [--top-n 20]                              (4축 유사도 → game_similarities_weekly)
        ▼
gca report [--game-id N]                                 (weekly_reports + markdown)
```

- 모든 단계는 `runs.track(stage, week_of)` context manager로 감싸져 `pipeline_runs`에 시작/성공/실패(에러 텍스트 2000자)와 rows_in/out이 기록됨 (`src/gca/pipeline/runs.py`).
- `--week-of` 미지정 시 ISO 주 월요일로 정규화 (`cli.py:_week_of`).
- `--changed-only`: features는 "현재 버전 없음 또는 `games.updated_at > valid_from`", embeddings는 "없음 또는 stale"만 재처리 → 증분 실행.

---

## 7. 기능별 상세 구현

### 7.1 Collectors — 플랫폼별 수집 (`src/gca/collectors/`)

공통 계약은 `base.py`의 `Collector` Protocol(`top_game_ids` / `fetch_game` / `fetch_reviews`). 모든 HTTP 호출은 tenacity `@retry(3회, exponential 1~8s)` + 커스텀 User-Agent.

| 플랫폼 | Top 목록 소스 | 상세 | 리뷰 | 필터링 |
|--------|--------------|------|------|--------|
| **Steam** | SteamSpy `top100in2weeks` (100 초과 시 `top100owned`, `top100forever` 합산) | `store.steampowered.com/api/appdetails` | `appreviews/{appid}` (recent, voted_up→10점/1점 매핑) | `type != "game"`(DLC/데모) 제외 |
| **App Store** | iTunes Search API — 키워드 5종("action game"…"sports game") × `genreId=6014` 합집합 | iTunes Lookup | RSS customerreviews (페이지 1~10, 1페이지 첫 entry는 앱 자신이라 skip) | `kind not in (software,…)` 제외 |
| **itch.io** | `itch.io/games/top-rated.json` 페이지네이션 | 공개 API `/api/1/.../game/{id}` (키 옵션) | **공개 리뷰 API 없음 → 빈 리스트** | `classification != game` 제외 |
| **Play Store** | 미구현 stub — curated seed 목록만 | `google-play-scraper` (optional deps) | 동일 라이브러리 | — |

수집 루프(`cli.py`)는 게임 단위 try/except로 한 게임 실패가 전체 배치를 막지 않음. 저장은 `raw_games`에 payload 전체를 JSONB로 `ON CONFLICT DO NOTHING`.

### 7.2 정규화 (`pipeline/normalize.py`)

- `SELECT DISTINCT ON (platform, external_id) ... ORDER BY collected_at DESC`로 **플랫폼별 최신 payload만** 선택.
- `extract_normalized(platform, payload)`가 플랫폼별 매핑:
  - steam: `steam_appid`, `short_description` 우선, `genres[].description + categories[].description` → `raw_tags`
  - appstore: `trackId`/`trackName`/`genres[]`
  - playstore: `appId`/`genre`+`genreId`
- `games`에 upsert — title/description/raw_tags 갱신 + `updated_at=NOW()` (이게 `--changed-only` 증분의 기준점이 됨).

### 7.3 LLM Feature 추출 (`pipeline/feature_extractor.py` + `feature_prompt.py`)

**입력**: title + description(3000자 절단) + 리뷰 최대 5개.
**모델**: Groq `llama-3.3-70b-versatile`, `response_format={"type":"json_object"}` (JSON 모드), max_tokens 1024.

추출 스키마 (프롬프트에 명시):

```json
{
  "genre": "RPG / Action / ...",
  "subgenre": "Roguelite / Tower Defense / ...",
  "bm_dist": {"gacha": 0~1, "ads": 0~1, "premium": 0~1, "sub": 0~1},  // 합=1.0
  "play_style": ["competitive", "casual", ...],
  "session_length_minutes": float,
  "core_loop": "1-2문장",
  "_canary_answer": "yes|no"
}
```

신뢰성 장치 3중:
1. **Canary 질문** — "이게 비디오 게임 맞나?"를 `_canary_answer`로 답하게 해 모델이 입력을 실제로 읽었는지 검증 (실패 시 warning 로그, `gca feature-quality`에서 pass rate 측정).
2. **필수 필드 검증** — 6개 필드 누락 시 결과 폐기(None 반환) → 해당 게임 skip.
3. **마크다운 펜스 제거 + JSON 파싱 가드** — 파싱 실패 시 폐기.

**캐싱**: `sha256(model + system + user_prompt)` 키로 `llm_cache` 조회 → 동일 입력 재호출 0원 (hit_count 증가). 저장은 검증 통과 후에만.

**저장 (SCD Type 2)**: `upsert_features`가 ① 현재 행 `valid_to=NOW()` 닫고 ② `feature_version+1`로 새 행 insert. `engine/features.py:get_features(game_id, as_of=...)`로 임의 시점의 feature를 조회 가능 — 주간 스냅샷 재현성 확보.

### 7.4 임베딩 (`pipeline/embedder.py`)

- `all-MiniLM-L6-v2` (384d)를 **모듈 전역 lazy 싱글톤**으로 로드.
- 게임당 2개 벡터: `description_embedding`(설명), `review_embedding`(리뷰 최대 10개 concat 8000자 — 리뷰 없으면 설명 벡터로 폴백).
- `embedding_cache`: `sha256(text+model)` 키 — 장르 문자열처럼 반복되는 짧은 텍스트("RPG" 등)는 사실상 1회만 인코딩됨.
- `game_embeddings`에 upsert.

### 7.5 유사도 엔진 — 핵심 (`engine/similarity.py`)

4축 연속값 유사도의 가중합:

```
score = w_semantic·cos(desc_a, desc_b)
      + w_genre   ·cos(embed(genre_a), embed(genre_b))
      + w_tier    ·exp(−|tier_a − tier_b| / 0.3)
      + w_bm      ·(1 − symKL(bm_a, bm_b) / 2log4)

DEFAULT_WEIGHTS = {semantic: 0.40, genre: 0.25, tier: 0.20, bm: 0.15}
```

| 축 | 의미 | 수식 디테일 |
|----|------|------------|
| **semantic** | 게임 설명의 의미적 유사성 | 코사인 (zero-vector 가드) |
| **genre** | 장르 근접성 | 장르 **문자열을 임베딩**해서 코사인 — "Roguelite" vs "Roguelike"처럼 категорial 매칭으론 0이 되는 케이스를 연속값으로 처리 |
| **tier** | 게임 규모(체급) 근접성 | `tier = log1p(리뷰 수) / max_log` 정규화 후 차이에 지수감쇠(σ=0.3) — 인디 vs AAA가 같은 장르여도 체급이 다르면 감점 |
| **bm** | 수익모델 유사성 | bm_dist 4-class 분포(gacha/ads/premium/sub)의 **대칭 KL divergence**를 [0,1] 정규화 후 1−x |

배치(`compute_all`):
- 대상: features(현재 버전) + embeddings 둘 다 있는 게임 전체.
- **base는 `is_my_game=TRUE`인 게임만** — 전체 N² 계산을 피하고 PM 관심 게임 기준으로만 계산.
- base당 전체 target과 점수 계산 → 정렬 → Top-N(기본 20)만 `game_similarities_weekly`에 rank와 함께 upsert.
- `component_scores` JSONB로 축별 점수를 저장 → FE 테이블/리포트에서 **"왜 유사한가"를 분해해서 보여줌** (설명가능성).
- 가중치는 `weight_history` 최신 행 사용 (`--default-weights`로 하드코딩 값 강제 가능).

### 7.6 가중치 자동 튜닝 (`engine/weight_tuner.py`)

PM 피드백을 랭킹 품질로 되먹임하는 부분:

1. **라벨 로딩**: `pm_feedback`(upvote/added=positive, downvote=negative) + `weak_similarities`(전부 positive).
2. **그리드 생성**: semantic/genre/tier 각각 0~1을 `n_steps`(기본 5) 분할, bm = 1−나머지 (합=1 제약) → 유효 조합 전수.
3. **평가**: 라벨이 있는 base 게임마다 해당 가중치로 전체 target 랭킹 → **NDCG@k**(기본 10, binary relevance) 평균.
4. **선택/저장**: 최고 평균 NDCG 조합을 `weight_history`에 저장 → 다음 `gca similarity`부터 자동 반영.

콜드스타트 가드: 라벨이 하나도 없으면 DEFAULT_WEIGHTS 반환.

### 7.7 Weak Labels — 콜드스타트 해결 (`engine/weak_labels.py`)

PM 피드백이 쌓이기 전 튜닝 라벨을 확보하는 3개 소스:

| 소스 | 방법 | 비고 |
|------|------|------|
| `steam_morelike` | Steam "More Like This" 페이지 HTML에서 `data-ds-appid` 정규식 추출 (최대 20개) | DB에 있는 steam 게임으로 resolve |
| `tag_overlap` | `games.raw_tags` 교집합 ≥ min_shared(기본 3)인 모든 쌍 | **완전 오프라인** — 네트워크 불필요 |
| `playstore_similar` | google-play-scraper `similar()` | optional deps |

저장 시 (a→b, b→a) **양방향** upsert로 대칭 커버리지 확보.

### 7.8 주간 리포트 (`report/weekly.py` + `templates/weekly.md.j2`)

`generate_report`가 빌드하는 데이터:
- **top_n**: 이번 주 `game_similarities_weekly` rank 순 (component_scores 포함)
- **new_entrants**: 전주(week_of − 7일) Top 목록에 없던 게임
- **rank_changes**: 전주 대비 순위 변동, |Δ| 내림차순
- **updates_summary**: 경쟁작 타이틀 목록을 Groq LLM에 보내 "PM 관점 주목할 업데이트 3-5 bullet" 생성 — **실패해도 리포트는 나감** (`_Summary unavailable._` 폴백)
- **weights**: 사용된 가중치 (투명성 — 리포트 푸터에 표기)

저장: JSONB로 `weekly_reports` upsert(주+게임당 1개) → 렌더는 조회 시점에 Jinja2로. 즉 **데이터와 표현 분리** — 템플릿 수정해도 과거 리포트 재렌더 가능. `gca report`는 단일 게임(markdown 파일 출력) / 전체(`is_my_game` 전부) 모드.

### 7.9 API (`api/server.py`, `api/routes/`)

FastAPI, CORS 전체 허용(GET/POST), 읽기 중심:

| 엔드포인트 | 동작 |
|-----------|------|
| `GET /health` | 헬스체크 |
| `GET /games?platform=&mine=&limit=&offset=` | 게임 목록 (my game 우선 정렬) |
| `POST /games/my {platform, appid}` | **FE의 게임 등록** — Steam에서 즉시 fetch → normalize → `is_my_game=TRUE` upsert. collector를 함수 내 지연 import (serverless 콜드스타트 보호) |
| `GET /competitors?base_game_id=&week_of=&limit=` | week_of 생략 시 `MAX(week_of)` 자동 해석. component_scores 포함 |
| `POST /feedback` | 시그널 4종 validation + 게임 존재 검증 후 insert |
| `GET /feedback/summary?base_game_id=` | (target, signal)별 집계 |
| `GET /reports?base_game_id=&format=json\|markdown` | 저장된 JSONB 반환 또는 즉석 markdown 렌더 |
| `POST /reports/generate?base_game_id=` | 온디맨드 리포트 생성 |

Vercel 배포: 루트 `vercel.json`이 `api/index.py`를 `@vercel/python`(3.11, 50MB, `includeFiles: src/**`)으로 빌드, 모든 경로를 라우팅, **region `icn1`(서울) 고정**(Supabase와 레이턴시 최소화). `api/index.py`는 `sys.path`에 `src/` 추가 후 app re-export만 수행.

### 7.10 FE (`web/`)

Next.js 16 App Router, 페이지 3개 — 전부 `dynamic = "force-dynamic"` (캐시 없는 SSR) + `loading.tsx` 스켈레톤:

1. **`/` My Games**: 서버 컴포넌트에서 `GET /games?mine=true` → 카드 그리드. `AddMyGameForm`(클라이언트)으로 Steam appid 등록 → `router.refresh()`.
2. **`/games/[id]` Competitors**: SSR로 Top 10 로드. `CompetitorsTable`(클라이언트)이 축별 점수를 **색상 코딩된 바 차트**(semantic=indigo, genre=emerald, tier=amber, bm=rose)로 시각화 + 스토어 딥링크. ▲▼ 버튼이 `POST /feedback`로 upvote/downvote 전송(낙관적 UI + 토스트) → 튜닝 라벨로 적재.
3. **`/games/[id]/report`**: `GET /reports?format=markdown` → react-markdown(+remark-gfm)로 커스텀 스타일 렌더. "Download PDF" = `window.print()` + print CSS.

API 클라이언트(`lib/api.ts`)는 `NEXT_PUBLIC_API_BASE_URL` 기반 타입드 fetch 래퍼(`cache: "no-store"`). 404 등은 페이지에서 **빈 상태 + 다음 실행할 CLI 명령 안내**로 처리 (예: "Run `gca similarity`").

### 7.11 품질 측정 (`gca feature-quality`)

gold fixture(YAML, `tests/fixtures/gold_features.yaml`)의 기대값과 LLM 추출 결과를 필드별 정확도(%)로 비교 + canary pass rate 출력 — 프롬프트 회귀 테스트 용도.

---

## 8. CLI 커맨드 요약 (`gca …`)

| 커맨드 | 역할 |
|--------|------|
| `migrate` | schema.sql 적용 |
| `collect:steam` / `collect:appstore` / `collect:itch` | 수집 (`--limit 200`, `--fetch-reviews`, `--review-limit`) |
| `normalize` | raw → games |
| `extract-features [--changed-only]` | LLM feature 추출 |
| `embed [--changed-only]` | 임베딩 생성 |
| `weak-labels --source tag_overlap\|steam` | 약한 라벨 수집 |
| `tune-weights [--n-steps 5] [--k 10]` | NDCG 그리드서치 |
| `similarity [--top-n 20] [--default-weights]` | 주간 유사도 계산 |
| `report [--game-id N] [--top-n 10]` | 리포트 생성 |
| `add-my-game --platform steam --appid <id>` | 분석 대상 등록 |
| `feature-quality [--fixture ...]` | 추출 품질 측정 |
| `status` | 테이블 카운트 + 최근 pipeline_runs |
| `serve [--port 8000]` | 로컬 FastAPI |

---

## 9. 핵심 설계 결정 정리

1. **Raw 보존 → 재처리 가능**: 외부 API 응답을 JSONB 그대로 시점별 저장. 정규화 로직이 바뀌어도 재수집 불필요.
2. **SCD Type 2 feature store**: LLM 출력이 바뀌어도 과거 주간 리포트의 입력을 시점 조회로 재현 가능.
3. **연속값 4축 + 설명가능성**: 카테고리 매칭 대신 전 축을 연속값으로 설계(장르조차 임베딩 코사인), 축별 점수를 저장해 FE/리포트에서 분해 표시.
4. **피드백 루프**: FE 투표 → pm_feedback → NDCG 그리드서치 → weight_history → 다음 주 similarity에 반영. 콜드스타트는 weak label 3종으로 해결.
5. **2중 캐시**: LLM·임베딩 모두 입력 해시 캐시 — 주간 재실행 시 변경 게임만 비용 발생. `--changed-only`와 합쳐 증분 파이프라인.
6. **배치/서빙 분리**: ML 의존성은 CLI에만, serverless API는 경량 읽기 전용 — Vercel 50MB 람다 제한 대응.
7. **idempotent 전 단계**: 모든 쓰기가 upsert/ON CONFLICT → 어떤 단계든 재실행 안전, `pipeline_runs`로 실패 추적.
