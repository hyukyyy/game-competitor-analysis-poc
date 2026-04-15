# Plan Implementation Status

원본 기획: `docs/plan.md` (아래 참고) 또는 원본 plan file
대화 내역: `docs/conversation.md`

**마지막 업데이트**: 2026-04-15 (Week 1 backbone 완료 시점)

---

## 요약

| Week | 목표 | 상태 |
|---|---|---|
| **Week 1** | 수집 + 스키마 + 정규화 | 🟢 Backbone 완료, DB 실행만 남음 |
| Week 2 | Feature 추출 (LLM) + 임베딩 | ⚪ 시작 전 |
| Week 3 | 유사도 엔진 + 가중치 튜닝 | ⚪ 시작 전 |
| Week 4 | 리포트 + 피드백 루프 | ⚪ 시작 전 |

---

## ✅ 구현 완료 (이 세션)

### 프로젝트 인프라
- `pyproject.toml` — hatchling build, `gca` entry point, dev+scrapers optional deps
- `conftest.py` — `src/` 자동 path 추가 (pytest install 없이도 테스트 가능)
- `.env.example` — 모든 env 변수 기본값
- `README.md` — setup + 4주 로드맵
- `.gitignore`

### 데이터 스키마 (`schema.sql`)
Postgres + pgvector 기반, 10개 테이블:
- `raw_games`, `raw_reviews` — 원본 보존 (평가 재처리 가능)
- `games` — 정규화 레이어, `(platform, external_id)` UNIQUE
- `game_features` — SCD Type 2 (`valid_from/valid_to`)
- `game_embeddings` — pgvector 1536
- `game_similarities_weekly` — 주간 스냅샷 (순위 변동 추적)
- `pm_feedback` — 암묵적 signal (upvote/downvote/clicked/added)
- `llm_cache`, `embedding_cache` — 비용 절감
- `pipeline_runs` — 관측성

### 수집 (`src/gca/collectors/`)
- `base.py` — `Collector` Protocol
- `steam.py` — **실제 동작 확인됨**
  - SteamSpy `top100in2weeks/top100owned/top100forever` 로 top N appids
  - `store.steampowered.com/api/appdetails` — 게임 상세
  - `store.steampowered.com/appreviews/{appid}` — 리뷰
  - tenacity 기반 재시도, 게임 외 type(DLC/Video 등) 필터링
  - Live test: CS2(730), Palworld(1172470), PUBG(578080) 등 fetch 확인
- `playstore.py` — **stub**: `google-play-scraper` 의존 (optional dep), seed list 기반 top IDs
- `appstore.py` — ⚪ 미구현 (iTunes Search API 계획)
- `itch.py` — ⚪ 미구현

### 파이프라인 (`src/gca/pipeline/`)
- `runs.py` — `track(stage, week_of)` 컨텍스트 매니저. `pipeline_runs` 자동 insert/update, 실패 시 status='failed' + error 텍스트.
- `normalize.py` — `extract_normalized(platform, payload)` + `normalize_all()`
  - 지원 플랫폼: steam / playstore / appstore
  - `DISTINCT ON (platform, external_id) ORDER BY collected_at DESC` 로 최신 원본만 UPSERT

### 핵심 모듈
- `config.py` — pydantic-settings, `.env` 자동 로드
- `db.py` — psycopg 3 + `dict_row`, 컨텍스트 매니저
- `logs.py` — `get_logger()` (stdlib 그림자 방지용 이름)
- `models.py` — Pydantic DTO (`RawGame`, `RawReview`, `NormalizedGame`)
- `cli.py` — argparse 기반, 4개 서브커맨드: `migrate`, `collect:steam`, `normalize`, `status`

### 테스트 (`tests/`)
- `test_normalize.py` — **6/6 pass**
  - Steam 기본, appid 없음, genres 없음, Play Store, App Store, 알 수 없는 플랫폼

---

## ⚠️ Week 1 잔여 (환경 세팅만 필요)

### 할 일
1. **Postgres + pgvector** 기동
   ```bash
   docker run -d --name gca-pg \
     -e POSTGRES_PASSWORD=postgres \
     -e POSTGRES_DB=game_competitor \
     -p 5432:5432 \
     pgvector/pgvector:pg16
   ```
2. `.env` 생성 (`DATABASE_URL` 확인)
3. 마이그레이션 + 실제 수집
   ```bash
   python -m gca.cli migrate
   python -m gca.cli collect:steam --limit 200 --fetch-reviews
   python -m gca.cli normalize
   python -m gca.cli status
   ```
4. `Deliverable`: 200개 게임의 `raw_games` + `games` 채움 확인

### 코드 보강 (시간 여유 시)
- `collectors/appstore.py` 실제 구현 (iTunes Search API, 공식 공개)
- `collectors/playstore.py`: seed 리스트 기반이 아닌 카테고리 top 자동화
- `collectors/itch.py`

---

## ⚪ Week 2 — Feature 추출 + 임베딩 (시작 전)

### 파일 만들 것
```
src/gca/pipeline/feature_extractor.py
src/gca/pipeline/embedder.py
src/gca/pipeline/cache.py          # llm_cache + embedding_cache helper
src/gca/engine/features.py         # Feature Store API (point-in-time lookup)
src/gca/pipeline/feature_prompt.py # 카나리 질문 + few-shot 포함
```

### 할 일
1. **LLM 호출 캐시 헬퍼** (`cache.py`)
   - `llm_cache_get(input_hash, model)` / `llm_cache_put(...)`
   - input_hash = sha256(model + prompt + content)
2. **Feature Extractor** (`feature_extractor.py`)
   - Input: `games.description` + 리뷰 샘플 3~5개
   - Output: `{genre, subgenre, bm_dist, play_style, session_length_minutes, core_loop}`
   - Claude API (`anthropic` SDK) 사용, `settings.llm_model`
   - 카나리 질문 1~2개 prompt에 삽입 → 정답률 모니터
   - `game_features` 에 SCD Type 2 UPSERT (`valid_to = NOW()` 기존 row, 새 row insert)
3. **Embedder** (`embedder.py`)
   - OpenAI `text-embedding-3-small` (1536)
   - description / review_concat 각각
   - `embedding_cache` 경유
4. **Feature Store API** (`engine/features.py`)
   - `get_features(game_id, as_of: datetime | None)` — point-in-time
   - `get_embedding(game_id, kind: 'description' | 'review')`
5. **Gold set** — PM 20개 수동 라벨 CSV/YAML fixture
   - `tests/fixtures/gold_features.yaml` (게임별 expected feature)
   - Self-consistency 스크립트: 같은 게임 3회 돌려 field 일치율

### CLI 추가
- `python -m gca.cli extract-features --changed-only`
- `python -m gca.cli embed --changed-only`
- `python -m gca.cli feature-quality` (gold set 대비 accuracy)

### Deliverable
- `game_features`, `game_embeddings` 채워짐
- Self-consistency >= 90% 리포트

---

## ⚪ Week 3 — 유사도 엔진 + 튜닝 (시작 전)

### 파일 만들 것
```
src/gca/engine/similarity.py
src/gca/engine/weight_tuner.py
src/gca/engine/weak_labels.py   # 플랫폼 similar 수집
```

### 공식 (초기값)
```python
score = (
    0.40 * cosine(desc_embed_a, desc_embed_b) +
    0.25 * cosine(genre_embed_a, genre_embed_b) +
    0.20 * exp(-abs(tier_a - tier_b) / sigma) +
    0.15 * (1 - kl_divergence(bm_dist_a, bm_dist_b))
)
```

### 할 일
1. **`similarity.compute_pair(a, b) -> (score, component_scores_json)`**
2. **주간 배치**: 200×200 pair 계산, `game_similarities_weekly` 에 저장
3. **캐시 전략**: 두 게임 모두 `feature_version` 안 바뀌면 전주 score 복사 (delta-only 재계산)
4. **Weak label 수집**: Steam "More Like This", Play Store "Similar apps" 크롤 → `weak_similarities` 임시 테이블
5. **Weight tuner** (`weight_tuner.py`)
   - Grid search on PM gold labels + weak labels
   - Objective: NDCG@10 or MAP
   - 결과: `weight_history` 테이블에 fit된 가중치 저장
6. **Explainability**: `component_scores` JSONB를 리포트에 노출

### CLI 추가
- `python -m gca.cli similarity --week-of=2026-04-13`
- `python -m gca.cli tune-weights`

### Deliverable
- 각 게임별 Top 20 경쟁작 랭킹
- Gold set 대비 precision@10 측정값 (목표 >= 0.6)

---

## ⚪ Week 4 — 리포트 + 피드백 루프 (시작 전)

### 파일 만들 것
```
src/gca/report/weekly.py
src/gca/report/templates/weekly.md.j2   # Jinja2 템플릿
src/gca/api/server.py                    # FastAPI
src/gca/api/routes/competitors.py
src/gca/api/routes/feedback.py
src/gca/api/routes/reports.py
frontend/                                 # Next.js 또는 최소 HTML
```

### 할 일
1. **Report generator** (`report/weekly.py`)
   - 섹션: Top 10, 신규 진입, 순위 변동, 주요 업데이트 요약 (LLM)
   - `weekly_reports` JSONB 에 저장
2. **FastAPI**
   - `GET /games`, `GET /competitors?base_game_id=&week_of=`
   - `GET /reports?base_game_id=&week_of=`
   - `POST /feedback` — `{base_game_id, target_game_id, week_of, signal}`
3. **FE (최소)**
   - 경쟁작 Top N 리스트 (component scores 포함)
   - 리포트 페이지
   - 👍/👎 버튼 → `pm_feedback`
4. **Slack delivery** (optional)
   - 주간 리포트를 Slack 채널로 (`incoming webhook`)

### Deliverable
- End-to-end 주간 리포트 1회 실제 발송
- upvote/downvote signal 실제 테이블 insert 확인

---

## 다른 환경에서 이어받을 때

### 1. 리포지토리 clone + venv
```bash
git clone <remote>
cd game-competitor-analysis-poc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. 현재 상태 검증
```bash
pytest tests/ -v                # 6/6 pass 여야 함
python -m gca.cli --help        # 4개 커맨드 노출
```

### 3. Week 1 마무리
- Postgres 띄우고 `.env` 설정 → `migrate` → `collect:steam` → `normalize`

### 4. Week 2 이어서
- 위 "⚪ Week 2" 섹션의 파일 리스트 + 할 일 순으로 진행

---

## 주요 설계 결정 (빠르게 훑기)

| 결정 | 내용 |
|---|---|
| 프레임 | 경쟁작 분석 도구 ❌ → 리서치팀 반복업무 자동화 ✅ |
| 성공 지표 | precision@N 아닌 "PM 리포트 준비 시간 X→Y" |
| 경쟁작 정의 | Target user overlap이 북극성. PoC는 4축 연속값 유사도로 근사 |
| 유사도 공식 | `0.40*semantic + 0.25*genre_embed + 0.20*tier + 0.15*bm_kl` (초기값, adaptive) |
| Ground truth | PM 라벨 20~50 + 플랫폼 similar signal (weak label) |
| HITL | 검수 단계 제거. upvote/downvote 암묵적 signal만 |
| 아키텍처 | Batch 2-stage (Collector/Normalizer) + Analysis 2-stage (Feature/Similarity) + API(read + /feedback) + FE |
| Feature Store | Postgres + pgvector + 얇은 Python API (Feast X) |
| 캐싱 | LLM + embedding + similarity 3단계, delta-only 재계산 |
| 데이터 소스 (PoC) | Steam/App Store/Play/itch.io |
| 메타 신호 (확장) | YouTube/Twitch — target user overlap 대리 지표 |
| 오케스트레이션 | Cron + Python (PoC) → Prefect (확장) |
