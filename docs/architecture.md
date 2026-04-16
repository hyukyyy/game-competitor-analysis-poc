# 시스템 아키텍처

## 전체 파이프라인 흐름

```
[Cron / 수동 실행 (주간)]
        │
        ▼
┌─────────────────────────────────────────────┐
│           Collectors                         │
│  steam │ appstore │ itch │ playstore(stub)  │
│                                              │
│  External APIs → raw_games, raw_reviews      │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│           Pipeline (ETL)                     │
│                                              │
│  normalize ─────→ games                      │
│       │                                      │
│       ├── feature_extractor ─→ game_features │
│       │     (Claude API)        (SCD Type 2) │
│       │     (llm_cache)                      │
│       │                                      │
│       └── embedder ──────────→ game_embeddings
│             (sentence-transformers)   (384d) │
│             (embedding_cache)                │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│           Engine (ML)                        │
│                                              │
│  similarity ────→ game_similarities_weekly   │
│    4축 가중합:                                │
│    - semantic 40% (cosine desc embeddings)   │
│    - genre    25% (cosine genre embeddings)  │
│    - tier     20% (gaussian session length)  │
│    - bm       15% (KL divergence bm_dist)   │
│                                              │
│  weight_tuner ──→ weight_history             │
│    (NDCG@10 grid search)                     │
│                                              │
│  weak_labels ───→ weak_similarities          │
│    (Steam morelike + tag overlap)            │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│           Report                             │
│                                              │
│  weekly.py ─────→ weekly_reports             │
│    (Jinja2 템플릿 + LLM 요약)                 │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│           API (FastAPI)                      │
│                                              │
│  GET  /games              게임 목록           │
│  GET  /competitors/{id}   경쟁작 Top N        │
│  GET  /reports/{id}       주간 리포트          │
│  POST /feedback           upvote/downvote    │
│                  │                           │
│                  ▼                           │
│            pm_feedback ──→ weight_tuner      │
│              (피드백 루프)                     │
└─────────────────────────────────────────────┘
```

---

## 디렉토리 구조

```
src/gca/
├── __init__.py
├── config.py              # Pydantic Settings (DB, API keys, 모델)
├── db.py                  # connect() context manager (psycopg)
├── logs.py                # get_logger() 싱글턴
├── models.py              # RawGame, RawReview, NormalizedGame
├── cli.py                 # 14개 서브커맨드 진입점
│
├── collectors/            # Layer 1: 데이터 수집
│   ├── base.py            #   Collector Protocol
│   ├── steam.py           #   SteamSpy + Steam Store API
│   ├── appstore.py        #   iTunes Search API
│   ├── playstore.py       #   google-play-scraper (stub)
│   └── itch.py            #   itch.io 공개 API
│
├── pipeline/              # Layer 2: ETL
│   ├── runs.py            #   pipeline_runs 추적 context manager
│   ├── normalize.py       #   raw_games → games (플랫폼별 파서)
│   ├── cache.py           #   llm_cache + embedding_cache 헬퍼
│   ├── feature_prompt.py  #   Claude 프롬프트 + canary 질문
│   ├── feature_extractor.py  # Claude → game_features (SCD Type 2)
│   └── embedder.py        #   sentence-transformers → game_embeddings
│
├── engine/                # Layer 3: ML 엔진
│   ├── features.py        #   Feature Store API (point-in-time lookup)
│   ├── similarity.py      #   4축 유사도 공식 + 주간 배치
│   ├── weight_tuner.py    #   NDCG@10 grid search
│   └── weak_labels.py     #   Steam morelike + tag overlap
│
├── report/                # Layer 4: 리포트
│   ├── weekly.py          #   리포트 생성/저장
│   └── templates/
│       └── weekly.md.j2   #   Jinja2 Markdown 템플릿
│
└── api/                   # Layer 5: API 서버
    ├── server.py          #   FastAPI app + CORS
    └── routes/
        ├── competitors.py #   GET /games, /competitors
        ├── feedback.py    #   POST /feedback
        └── reports.py     #   GET /reports
```

---

## DB 테이블 (13개)

### Layer별 소유권

| Layer | Writes | Reads |
|---|---|---|
| Collectors | `raw_games`, `raw_reviews` | — |
| Pipeline/normalize | `games` | `raw_games` |
| Pipeline/feature_extractor | `game_features`, `llm_cache` | `games`, `raw_reviews` |
| Pipeline/embedder | `game_embeddings`, `embedding_cache` | `games`, `raw_reviews` |
| Engine/similarity | `game_similarities_weekly` | features, embeddings, weights |
| Engine/weight_tuner | `weight_history` | `pm_feedback`, `weak_similarities` |
| Engine/weak_labels | `weak_similarities` | `games`, `game_features` |
| Report | `weekly_reports` | similarities, games |
| API | `pm_feedback` (유일한 write) | 전체 read |
| 공통 | `pipeline_runs` (모든 stage) | — |

### 테이블 목적

```
raw_games ──────── 플랫폼 원본 payload (JSONB)
raw_reviews ────── 리뷰 원본 (text, rating)
games ──────────── 정규화된 게임 정보
game_features ──── LLM 추출 feature (SCD Type 2: valid_from/valid_to)
game_embeddings ── 벡터 임베딩 (vector(384))
game_similarities_weekly ── 주간 유사도 스냅샷 + 순위
pm_feedback ────── PM upvote/downvote signal
llm_cache ──────── LLM 호출 캐시 (SHA256 → JSONB)
embedding_cache ── 임베딩 캐시 (text hash → vector)
pipeline_runs ──── stage별 실행 이력
weekly_reports ─── 생성된 리포트 (JSONB)
weight_history ─── 튜닝된 가중치 이력
weak_similarities ─ 플랫폼 "similar games" signal
```

---

## 유사도 공식

```python
score = (
    w_semantic * cosine(desc_embed[a], desc_embed[b])     # 0.40
  + w_genre    * cosine(genre_embed[a], genre_embed[b])    # 0.25
  + w_tier     * exp(-|tier(a) - tier(b)| / sigma)         # 0.20
  + w_bm       * (1 - KL_sym(bm_dist[a], bm_dist[b]))     # 0.15
)
```

가중치는 `tune-weights`로 PM feedback + weak label 기반 grid search 자동 튜닝.

---

## 피드백 루프

```
PM이 리포트에서 upvote/downvote
        ↓
    pm_feedback 테이블
        ↓
    weight_tuner (주간)
        ↓
    weight_history → 유사도 공식 가중치 갱신
        ↓
    다음 주 리포트 품질 개선
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3.12 |
| DB | PostgreSQL 16 + pgvector 0.8.2 |
| LLM | Claude Sonnet (Anthropic SDK) |
| 임베딩 | sentence-transformers `all-MiniLM-L6-v2` (384d, 로컬) |
| API | FastAPI + uvicorn |
| 템플릿 | Jinja2 |
| HTTP | httpx + tenacity retry |
| 컨테이너 | Docker (`gca-pg`, 포트 55432) |
