# 구현 내용 & 미검증 항목 정리

작성일: 2026-04-15  
상태: **코드 완료 — 실행환경(Python + DB) 미세팅으로 런타임 테스트 미완**

---

## 1. 프로젝트 개요

게임 회사 리서치팀의 **주간 경쟁작 리포트 작성을 자동화**하는 내부 도구.

- 플랫폼: Steam / App Store / itch.io (Play Store는 stub)
- 대상 게임: 상위 200개
- 주기: 주간 배치
- 핵심 기술: Claude (feature 추출), OpenAI (임베딩), pgvector (유사도), FastAPI (API)

---

## 2. 전체 파일 구조

```
src/gca/
├── config.py                        # Pydantic Settings (.env 로드)
├── db.py                            # psycopg3 연결 context manager
├── logs.py                          # 로거
├── models.py                        # Pydantic DTO (RawGame, RawReview, NormalizedGame)
├── cli.py                           # CLI 진입점 — 14개 서브커맨드
│
├── collectors/
│   ├── base.py                      # Collector Protocol
│   ├── steam.py                     # ✅ Steam Web API + SteamSpy (live test 완료)
│   ├── appstore.py                  # ✅ iTunes Search API (공식 공개)
│   ├── playstore.py                 # 🟡 stub (google-play-scraper 선택적 의존)
│   └── itch.py                      # ✅ itch.io 공개 API
│
├── pipeline/
│   ├── runs.py                      # ✅ pipeline_runs 추적 context manager
│   ├── normalize.py                 # ✅ raw → games UPSERT
│   ├── cache.py                     # ✅ llm_cache / embedding_cache DB helper
│   ├── feature_prompt.py            # ✅ Claude 프롬프트 템플릿 + canary 질문
│   ├── feature_extractor.py         # ✅ Claude API → game_features (SCD Type 2)
│   └── embedder.py                  # ✅ OpenAI → game_embeddings
│
├── engine/
│   ├── features.py                  # ✅ Feature Store API (point-in-time lookup)
│   ├── similarity.py                # ✅ 4축 유사도 공식 + 주간 배치 계산
│   ├── weight_tuner.py              # ✅ NDCG@10 grid search + weight_history 저장
│   └── weak_labels.py               # ✅ Steam morelike + tag overlap 수집
│
├── report/
│   ├── weekly.py                    # ✅ 리포트 생성 / Jinja2 렌더링 / DB 저장
│   └── templates/weekly.md.j2       # ✅ Markdown 템플릿 (Top 10 / 신규 / 순위변동)
│
└── api/
    ├── server.py                    # ✅ FastAPI app + CORS
    └── routes/
        ├── competitors.py           # ✅ GET /games, GET /competitors
        ├── feedback.py              # ✅ POST /feedback, GET /feedback/summary
        └── reports.py               # ✅ GET /reports, POST /reports/generate

schema.sql                           # ✅ 12개 테이블 (pgvector 포함)
tests/
├── test_normalize.py                # ✅ 6/6 pass (normalize 유닛 테스트)
└── fixtures/gold_features.yaml      # ✅ 20개 PM 라벨 gold set
```

---

## 3. 주간 실행 파이프라인

```
[Cron / 수동]
    ↓
collect:steam / collect:appstore / collect:itch
    ↓ raw_games, raw_reviews
normalize
    ↓ games
extract-features          (Claude API — 캐시 경유)
    ↓ game_features (SCD Type 2)
embed                     (OpenAI API — 캐시 경유)
    ↓ game_embeddings
weak-labels               (tag_overlap 또는 Steam morelike)
    ↓ weak_similarities
tune-weights              (NDCG@10 grid search, 선택적)
    ↓ weight_history
similarity                (4축 유사도 계산)
    ↓ game_similarities_weekly
report                    (Jinja2 + Claude 요약)
    ↓ weekly_reports
serve                     (FastAPI 서버 — FE / PM이 조회)
```

---

## 4. CLI 서브커맨드 목록

| 커맨드 | 설명 |
|---|---|
| `migrate` | schema.sql 적용 |
| `collect:steam --limit 200 --fetch-reviews` | Steam 수집 |
| `collect:appstore --limit 200` | App Store 수집 |
| `collect:itch --limit 100` | itch.io 수집 |
| `normalize` | raw → games 정규화 |
| `extract-features [--changed-only]` | Claude feature 추출 |
| `embed [--changed-only]` | OpenAI 임베딩 생성 |
| `feature-quality [--fixture path]` | gold set 대비 accuracy 측정 |
| `weak-labels --source tag_overlap\|steam` | weak label 수집 |
| `tune-weights [--n-steps 5]` | 가중치 grid search |
| `similarity [--week-of YYYY-MM-DD]` | 유사도 계산 + 저장 |
| `report [--game-id N]` | 주간 리포트 생성 |
| `serve [--port 8000]` | FastAPI 서버 실행 |
| `status` | 파이프라인 상태 조회 |

---

## 5. API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/games` | 게임 목록 (platform 필터 가능) |
| GET | `/competitors?base_game_id=&week_of=` | 경쟁작 Top N + component scores |
| POST | `/feedback` | PM upvote/downvote/clicked/added 기록 |
| GET | `/feedback/summary?base_game_id=` | 피드백 집계 |
| GET | `/reports?base_game_id=&format=json\|markdown` | 리포트 조회 |
| POST | `/reports/generate?base_game_id=` | 온디맨드 리포트 생성 |
| GET | `/health` | 헬스체크 |

---

## 6. 유사도 공식

```python
score = (
    w_semantic * cosine(desc_embed_a, desc_embed_b)          # default 0.40
  + w_genre    * cosine(genre_embed_a, genre_embed_b)         # default 0.25
  + w_tier     * exp(-|tier_a - tier_b| / 0.3)                # default 0.20
  + w_bm       * (1 - KL_symmetric(bm_dist_a, bm_dist_b))    # default 0.15
)
```

- **semantic**: games.description OpenAI 임베딩 cosine
- **genre**: LLM 추출 genre 문자열 임베딩 cosine
- **tier**: log(review_count) 정규화 후 exponential 거리
- **bm**: `{gacha, ads, premium, sub}` 확률분포 symmetric KL divergence

가중치는 `tune-weights`로 주 1회 자동 튜닝 → `weight_history` 저장, 다음 실행 시 자동 로드.

---

## 7. DB 스키마 요약 (12개 테이블)

| 테이블 | 용도 |
|---|---|
| `raw_games` | 플랫폼 원본 JSON 보존 (JSONB) |
| `raw_reviews` | 원본 리뷰 (재처리 가능) |
| `games` | 정규화 레이어, `(platform, external_id)` UNIQUE |
| `game_features` | SCD Type 2 (`valid_from/valid_to`) |
| `game_embeddings` | pgvector 1536 (description + review) |
| `game_similarities_weekly` | 주간 스냅샷 + component_scores JSONB |
| `pm_feedback` | upvote/downvote/clicked/added signal |
| `llm_cache` | sha256(model+prompt+content) → output |
| `embedding_cache` | sha256(text+model) → vector |
| `pipeline_runs` | stage별 실행 이력 (observability) |
| `weekly_reports` | 생성된 리포트 JSONB |
| `weight_history` | 튜닝된 가중치 이력 |
| `weak_similarities` | 플랫폼 similar signal (steam_morelike / tag_overlap) |

---

## 8. 환경 문제로 테스트 못한 항목

### 8-1. 실행환경 미세팅 (Python 미설치)

이 컴퓨터에 Python이 설치되어 있지 않아 (`python` 커맨드가 Windows Store stub) 아래 항목들을 런타임에서 검증하지 못했다.

---

### 8-2. DB 연동 테스트 미완

**미검증 항목:**

| 항목 | 파일 | 검증 방법 |
|---|---|---|
| `migrate` 실행 | `cli.py` | `gca migrate` 후 `\dt` 로 12개 테이블 확인 |
| `collect:steam` DB insert | `cli.py` | `gca status` 로 raw_games 행 수 확인 |
| `normalize` UPSERT | `pipeline/normalize.py` | games 테이블 행 수 확인 |
| `feature_extractor` SCD Type 2 | `pipeline/feature_extractor.py` | 같은 game 2회 실행 후 valid_to 설정 확인 |
| `embedder` pgvector insert | `pipeline/embedder.py` | `SELECT description_embedding IS NOT NULL` 확인 |
| `similarity` 배치 계산 | `engine/similarity.py` | game_similarities_weekly 행 수 확인 |
| `weight_tuner` grid search | `engine/weight_tuner.py` | pm_feedback / weak_similarities 데이터 있을 때만 의미 있음 |
| `report` Jinja2 렌더링 | `report/weekly.py` | 출력 Markdown 파일 직접 확인 |
| FastAPI 서버 기동 | `api/server.py` | `GET /health` 200 확인 |

---

### 8-3. 외부 API 연동 테스트 미완

| API | 파일 | 알려진 리스크 |
|---|---|---|
| Steam Web API | `collectors/steam.py` | **live test 완료** (CS2, Palworld 등 fetch 확인) |
| iTunes Search API | `collectors/appstore.py` | 미검증 — 공식 공개 API라 구조 변경 위험 낮음 |
| itch.io API | `collectors/itch.py` | 미검증 — keyless 엔드포인트가 실제 game 데이터 반환하는지 확인 필요 |
| Claude API (Anthropic) | `pipeline/feature_extractor.py` | 미검증 — JSON 파싱 실패 케이스 있을 수 있음 |
| OpenAI Embeddings | `pipeline/embedder.py` | 미검증 — pgvector insert 시 타입 호환 확인 필요 |
| Steam "More Like This" HTML | `engine/weak_labels.py` | 미검증 — HTML scraping이라 구조 변경에 취약 |

---

### 8-4. 알려진 잠재적 버그

**`feature_extractor.py` — Claude JSON 파싱**
- Claude가 JSON 앞뒤에 markdown 코드블록(` ```json `)을 붙이는 경우 `json.loads()` 실패
- 수정 방법: 파싱 전 정규식으로 코드블록 제거
```python
import re
raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
```

**`embedder.py` — pgvector 타입**
- psycopg3에서 `list[float]` 를 `vector` 컬럼에 직접 insert 시 타입 어댑터 등록 필요할 수 있음
- 수정 방법: `pgvector` 패키지의 `register_vector(conn)` 호출 추가

**`similarity.py` — `get_embedding` import 순환 가능성**
- `engine/similarity.py`가 `pipeline/embedder.py`를 import → `pipeline/__init__.py`가 모든 모듈을 import하므로 순환 위험
- 확인 필요: `python -c "from gca.engine import similarity"` 로 import 에러 체크

**`weight_tuner.py` — 라벨 없을 때**
- `pm_feedback`와 `weak_similarities` 가 모두 비어있으면 default weights 반환 (정상 동작)
- 단, `grid_search()` 시작 시 명확한 로그 메시지로 확인 가능

**`itch.py` — keyless API 엔드포인트**
- `/api/1/key/game/{id}` 엔드포인트는 공식 문서에 없는 패턴
- 실제로는 `/api/1/{api_key}/game/{id}` 만 동작할 수 있음
- `ITCH_API_KEY` 없이 사용 시 404 가능 → `top_game_ids()`로 ID만 수집하고 fetch_game은 skip하는 방향으로 수정 필요할 수 있음

---

### 8-5. 검증되지 않은 통합 흐름

아래 end-to-end 흐름은 코드 수준에서 연결되어 있으나 실제 실행 검증 미완:

1. `extract-features` → `embed` → `similarity` → `report` 순서 정상 실행
2. `POST /feedback` → `tune-weights` → 다음 주 `similarity` 에서 새 가중치 반영
3. `feature-quality` 커맨드가 `gold_features.yaml` 올바르게 파싱 후 accuracy 출력

---

## 9. 환경 세팅 후 검증 순서

```bash
# 1. 환경 세팅
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

docker run -d --name gca-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=game_competitor \
  -p 5432:5432 \
  pgvector/pgvector:pg16

cp .env.example .env
# .env 에 ANTHROPIC_API_KEY, OPENAI_API_KEY, STEAM_API_KEY 설정

# 2. 기존 테스트 통과 확인
pytest tests/ -v   # 6/6 pass 여야 함

# 3. 파이프라인 단계별 검증
python -m gca.cli migrate
python -m gca.cli collect:steam --limit 10 --fetch-reviews   # 소량 먼저
python -m gca.cli normalize
python -m gca.cli status   # raw_games, games 행 수 확인

python -m gca.cli extract-features --changed-only   # Claude 호출 — 소량 먼저
python -m gca.cli embed --changed-only

python -m gca.cli weak-labels --source tag_overlap
python -m gca.cli similarity --week-of $(date +%Y-%m-%d)

python -m gca.cli report --week-of $(date +%Y-%m-%d) --game-id 1

python -m gca.cli serve &
curl http://localhost:8000/health
curl "http://localhost:8000/competitors?base_game_id=1"

# 4. 전체 200개로 확장
python -m gca.cli collect:steam --limit 200 --fetch-reviews
python -m gca.cli collect:appstore --limit 200
python -m gca.cli collect:itch --limit 100
```

---

## 10. 추가 개발 여지 (PoC 이후)

| 항목 | 설명 |
|---|---|
| Play Store 수집 | `collectors/playstore.py` stub → 실제 구현 필요 (현재 seed list 기반) |
| Claude JSON 파싱 강화 | 코드블록 strip + retry with `json_mode` |
| pgvector 타입 어댑터 | `register_vector()` 명시적 등록 |
| Slack 리포트 발송 | `report/weekly.py` 에 webhook 전송 추가 |
| Prefect 오케스트레이션 | 현재 CLI 수동 → Prefect flow 전환 |
| 유튜브 시청자 overlap | `collectors/youtube.py` — target user overlap 최고 대리 지표 |
| 운영 DB 마이그레이션 | Alembic 도입 권장 (현재 schema.sql 직접 실행) |
