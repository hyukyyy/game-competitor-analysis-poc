# 게임 경쟁작 자동 분석 시스템 — PoC 개발 기획 (v2)

## Context

**이건 게임 분석 도구를 만드는 프로젝트가 아니다.** 게임 회사 리서치팀의 **반복 업무(주간 경쟁작 리서치 & 리포트 작성)를 자동화**하는 내부 생산성 프로젝트다.

### 왜 이 프레임이 중요한가
- 목적함수가 "경쟁작을 정확히 맞추기"가 아니라 **"PM이 월요일 아침 10분 안에 시장 현황 파악"** 이 된다.
- 성공 지표가 precision@N이 아니라 **"리포트 준비 시간 X시간 → Y시간"** 으로 바뀐다.
- 경쟁작을 "확정"할 필요 없다. **리포트의 후보로 제시**하고 PM이 취사선택하면 충분하다.

### 범위
- 모바일(Play Store) + PC(Steam) 기준
- Top 게임 약 200개
- 주간 배치
- PoC = 1개월, 운영 전환 별도

---

## 경쟁작 정의 (PoC 기준)

**"target user 층이 겹치는 정도"** 를 본질 지표로 삼되, PoC에서는 직접 측정이 어렵기 때문에 **4개 축의 연속값 유사도**로 근사한다.

| 축 | 표현 방식 | 가중치 (초기) |
|---|---|---|
| Semantic similarity | description + review embedding cosine | 0.40 |
| Tier similarity | review count/rating/price bucket의 연속 거리 | 0.20 |
| Genre/subgenre | LLM 추출 후 embedding cosine (카테고리 원-핫 X) | 0.25 |
| BM | gacha/ads/premium/sub 확률분포 KL 거리 | 0.15 |

**동일 장르 제약 제거**, **"기타" 제거**, **카테고리 이진 매칭 대신 연속값** 사용.

### Ground Truth
1. **PM 수동 라벨 20~50개 게임** (각 "진짜 경쟁작 top 5")
2. **Platform "similar games" signal** (Steam More Like This, Play Similar) — weak label
3. 가중치는 위 두 신호에 fit (grid search 또는 간단한 learning-to-rank)

---

## 데이터 소스 현실

### PoC 메인 (Week 1~2)
| 소스 | 사용 여부 | 용도 |
|---|---|---|
| Steam Web API (appdetails, appreviews) | ✅ 공식 | PC 게임 메타/리뷰 |
| SteamSpy | ✅ 보조 | 플레이타임/owner 추정 |
| **App Store (iTunes Search + app-store-scraper)** | ✅ **추가 — 모바일 반쪽 보강** | iOS 모바일 메타/리뷰 |
| Play Store (gplay-scraper) | △ 비공식 — PoC 한정 | Android 모바일 메타/리뷰 |
| itch.io API | ✅ 공식, 가벼움 | 인디 조기 트렌드 |

### 메타 시그널 소스 (Week 4 or 확장) — target user overlap 대리 지표
| 소스 | 시그널 | 비고 |
|---|---|---|
| **YouTube Data API** | 게임별 검색량, 시청자 겹침 | ⭐ target user overlap 최고 대리 지표 |
| Twitch API | Concurrent viewers, 공동 시청자 | 살아있는지 + 유저 흐름 |
| SteamDB | Concurrent players 시계열 | Steam에 한정 |
| Google Trends | 검색 트렌드 | 시장 관심도 |

### 확장 단계 (PoC 이후)
- **AppMagic / SensorTower / data.ai**: revenue/DAU/cross-install — 운영 전환 시 라이선스
- **TapTap**: 중화권/아시아 모바일 (회사 타겟 시장 따라)
- **Epic Games Store / 콘솔 스토어**: 타겟 플랫폼 따라

### AI 간접 측정
- Description + screenshots → multimodal LLM으로 genre/BM/playstyle 추출
- Review 텍스트 → session_length / pain point / 유저 세그먼트 추론
- 아이콘/UI 이미지 → 아트 스타일 분류
- ASO 키워드 → 타겟 유저 추론

---

## 서버 아키텍처

사용자 초안 기준으로 아래 보강:
- **Batch server를 Collector / Normalizer 2개 stage로 분리** — 실패 원인이 달라서 재시도 단위가 다름
- **Analysis server를 Feature Extractor / Similarity Engine 2개로 분리** — LLM(비쌈) vs numpy(저렴) 재계산 주기가 다름
- **API server에 `POST /feedback`만 write 허용** — PM upvote/downvote 수집용, 나머진 read-only

```
[Cron / EventBridge (weekly)]
   ↓
[Collector (Lambda / batch)]
   ↓  raw_games, raw_reviews
[Normalizer (Lambda / batch)]
   ↓  games
[Feature Extractor (Python + LLM)]
   ↓  game_features (SCD Type 2), game_embeddings
[Similarity Engine (Python + numpy)]
   ↓  game_similarities_weekly (주간 스냅샷)
[Report Generator (Python + LLM)]
   ↓  weekly_reports

[API Server (FastAPI)]
  GET  /games, /competitors, /reports      ← FE 조회
  POST /feedback                           ← FE upvote/downvote → pm_feedback

[FE (Next.js)]
  - 경쟁작 Top N 리스트
  - 리포트 뷰
  - upvote/downvote 버튼 (유일한 write 경로)
```

피드백 루프: `pm_feedback` → Weight Tuner(주간) → 유사도 공식 가중치 갱신

---

## 스키마 (Minor 수정 반영)

```sql
-- 원본
CREATE TABLE raw_games (
  id SERIAL PRIMARY KEY,
  platform VARCHAR NOT NULL,
  external_id VARCHAR NOT NULL,
  payload JSONB NOT NULL,          -- 플랫폼 응답 통째
  collected_at TIMESTAMP NOT NULL,
  UNIQUE (platform, external_id, collected_at)
);

-- 리뷰는 별도 테이블 (row 비대화 방지)
CREATE TABLE raw_reviews (
  id BIGSERIAL PRIMARY KEY,
  platform VARCHAR NOT NULL,
  external_id VARCHAR NOT NULL,
  review_id VARCHAR NOT NULL,
  text TEXT,
  rating INT,
  posted_at TIMESTAMP,
  collected_at TIMESTAMP NOT NULL,
  UNIQUE (platform, review_id)
);

-- 정규화
CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  platform VARCHAR NOT NULL,
  external_id VARCHAR NOT NULL,
  title TEXT,
  description TEXT,
  raw_tags TEXT[],
  updated_at TIMESTAMP NOT NULL,
  UNIQUE (platform, external_id)
);

-- Feature (SCD Type 2로 시계열 유지)
CREATE TABLE game_features (
  id SERIAL PRIMARY KEY,
  game_id INT NOT NULL REFERENCES games(id),
  genre VARCHAR,
  subgenre VARCHAR,
  bm_dist JSONB,                   -- {gacha:0.6, ads:0.2, premium:0.1, sub:0.1}
  play_style TEXT[],
  session_length_minutes FLOAT,    -- 연속값
  core_loop TEXT,
  feature_version INT NOT NULL,
  valid_from TIMESTAMP NOT NULL,
  valid_to TIMESTAMP,              -- NULL = 현재 유효
  UNIQUE (game_id, valid_from)
);

-- 임베딩 (pgvector)
CREATE TABLE game_embeddings (
  game_id INT PRIMARY KEY REFERENCES games(id),
  description_embedding VECTOR(1536),
  review_embedding VECTOR(1536),
  updated_at TIMESTAMP NOT NULL
);

-- 주간 스냅샷 (순위 변동 추적)
CREATE TABLE game_similarities_weekly (
  week_of DATE NOT NULL,           -- 주 단위 파티션 키
  base_game_id INT NOT NULL,
  target_game_id INT NOT NULL,
  similarity_score FLOAT NOT NULL,
  rank INT NOT NULL,
  component_scores JSONB,          -- {semantic:0.8, tier:0.6, ...} for explainability
  calculated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (week_of, base_game_id, target_game_id)
);

-- PM 피드백 (암묵적 feedback → 가중치 학습)
CREATE TABLE pm_feedback (
  id BIGSERIAL PRIMARY KEY,
  base_game_id INT NOT NULL,
  target_game_id INT NOT NULL,
  week_of DATE NOT NULL,
  signal VARCHAR NOT NULL,         -- 'upvote' / 'downvote' / 'clicked' / 'added'
  user_id VARCHAR,
  created_at TIMESTAMP NOT NULL
);
```

---

## Feature 품질 측정 (Q6 아이디어 → 실제 구현)

1. **Gold set 구축**: PM이 20개 게임의 feature 수동 라벨 → LLM 출력과 field-wise accuracy
2. **Self-consistency 모니터**: 같은 게임 3회 샘플링해 카테고리 일치율 (목표 >90%)
3. **Canary questions**: 프롬프트에 정답 알려진 yes/no 질문 섞어 주간 오답률 추적
4. **Downstream proxy**: PM upvote rate를 feature 품질 대리 지표로 모니터
5. **Cross-model spot check** (월간): Claude vs GPT-4 출력 비교해 divergent 케이스 flag

---

## 유사도 공식 (연속값 기반)

```python
score = (
    0.40 * cosine(desc_embed[a], desc_embed[b]) +
    0.25 * cosine(genre_embed[a], genre_embed[b]) +
    0.20 * exp(-|tier(a) - tier(b)| / sigma) +
    0.15 * (1 - kl_divergence(bm_dist[a], bm_dist[b]))
)
```

- 초기 가중치는 위 값으로 시작
- 주기적으로 PM 라벨 + 플랫폼 similar 신호로 **grid search 재튜닝** (adaptive)
- component_scores를 리포트에 함께 노출 → **설명가능성** 확보

---

## 주간 리포트 구조

1. **경쟁작 Top 10** (score + 각 component 점수 + 왜 경쟁작인지 1줄 rationale LLM 생성)
2. **신규 진입 경쟁작** (지난 주 없던 게임)
3. **순위 변동** (week_of 2개 비교)
4. **주요 업데이트 요약** (update log LLM 요약)
5. **각 항목에 upvote/downvote 버튼** → `pm_feedback` 테이블로

---

## HITL 재설계

- **"검수 → 승인" 플로우 제거** (일 2번 하는 문제 해결)
- PM은 리포트만 소비 + 클릭/upvote/수동 추가 등 **암묵적 signal**만 남김
- 그 signal이 주 단위로 **가중치 재학습**에 들어감
- 검수는 "일"이 아니라 "데이터 생산"으로 전환됨

---

## 4주 개발 일정

### Week 1 — 수집 + 스키마
- Steam Web API collector
- Play Store 스크래퍼 (PoC 한정)
- raw_* / games 테이블 구축
- **Deliverable**: 200개 게임의 raw 데이터 확보

### Week 2 — Feature 추출 + 임베딩
- LLM feature 추출 파이프라인 (Claude)
- description/review 임베딩 생성 (pgvector)
- Gold set 20개 PM 라벨 수집
- Canary questions 프롬프트 삽입
- **Deliverable**: `game_features`, `game_embeddings` 채움 + self-consistency 리포트

### Week 3 — 유사도 엔진 + 튜닝
- 유사도 공식 구현
- 플랫폼 similar signal 수집 → weak label
- Grid search로 가중치 fit
- `game_similarities_weekly` 주간 스냅샷 저장
- **Deliverable**: Top 20 경쟁작 랭킹, precision@10 측정값

### Week 4 — 리포트 + 피드백 루프
- 리포트 생성 (LLM + 템플릿)
- Slack/웹 전달
- upvote/downvote 버튼 + `pm_feedback` 수집
- **Deliverable**: 엔드-투-엔드 주간 리포트 1회 실제 발송

---

## 성공 지표 (PoC)

| 지표 | 목표 |
|---|---|
| 주간 리포트 준비 시간 (PM 측) | 현재 X시간 → 1시간 이내 |
| Top 10 precision (gold set 대비) | ≥ 0.6 |
| PM upvote rate | ≥ 50% |
| Feature self-consistency | ≥ 90% |
| 파이프라인 end-to-end 주간 실행 성공률 | ≥ 95% |

---

## 리스크 & 대응

| 리스크 | 단계 | 대응 |
|---|---|---|
| Play Store 스크래핑 ToS | 운영 전환 | PoC에선 사내 사용만. 운영 전환 시 AppMagic/SensorTower 라이선스 검토 |
| LLM feature 정확도 | Week 2~ | Gold set + self-consistency 모니터링 |
| Ground truth 부재 | Week 1~ | PM 라벨링 20개 + 플랫폼 similar signal weak label |
| PM 피드백 sparsity | Week 4~ | Upvote뿐 아니라 클릭/체류시간도 signal로 |
| 200개가 너무 적어 통계 약함 | PoC 내내 | 후보군을 1000개로 확장, rank만 200 |

---

## 데이터 파이프라인 + Feature Store + 결과 캐싱 구체 설계

### A. 데이터 파이프라인

**PoC 오케스트레이션 선택**:
| 옵션 | 권장도 |
|---|---|
| Cron + Python script | ⭐ PoC 시작 — 주간 배치면 충분 |
| Prefect | Week 3+ 확장 시 (Airflow보다 세팅 간단) |
| AWS Step Functions + Lambda | 풀 서버리스 요구 시 |
| Airflow | 오버킬 — PoC 탈출 후 |

**핵심 원칙**:
- **멱등성**: 모든 stage는 `(platform, external_id, week_of)` 기준 UPSERT
- **실패 격리**: stage별 독립 테이블로 이전 stage 결과 보존 → 실패한 stage만 재실행
- **관측성**: `pipeline_runs` 테이블에 stage별 start/end/status/rows 기록

```sql
CREATE TABLE pipeline_runs (
  id BIGSERIAL PRIMARY KEY,
  stage VARCHAR NOT NULL,
  week_of DATE NOT NULL,
  status VARCHAR NOT NULL,           -- running/success/failed
  rows_in INT, rows_out INT,
  started_at TIMESTAMP, ended_at TIMESTAMP,
  error TEXT
);
```

### B. Feature Store

**PoC는 풀스케일 Feast/Tecton 쓰지 말고 Postgres + pgvector + 얇은 Python API로 충분.**

필수 3기능:
1. **버저닝 (SCD Type 2)** — `valid_from/valid_to`로 feature 이력 유지, 과거 리포트 재현 가능
2. **Point-in-time lookup** — `get_features(game_id, as_of=...)` 로 특정 시점 feature 조회
3. **단일 접근 API** — 모든 downstream(Similarity, Report)이 이 API만 사용, 나중에 마이그레이션 자유

**구현 총량**: Python 파일 1개 (~150줄), 테이블 2개 (`game_features`, `game_embeddings`)

```python
# features.py (스케치)
def get_features(game_id: int, as_of: datetime = None) -> Features: ...
def upsert_features(game_id: int, features: Features, version: int) -> None: ...
def get_embedding(game_id: int, kind: str) -> Vector: ...
```

### C. 결과 캐싱 (3단계)

**① LLM 호출 캐시** (비용의 70%+ 절감)
```sql
CREATE TABLE llm_cache (
  input_hash VARCHAR PRIMARY KEY,    -- sha256(prompt + description + model)
  model VARCHAR NOT NULL,
  output JSONB NOT NULL,
  created_at TIMESTAMP NOT NULL,
  hit_count INT DEFAULT 0
);
```

**② 임베딩 캐시**
```sql
CREATE TABLE embedding_cache (
  text_hash VARCHAR PRIMARY KEY,
  model VARCHAR NOT NULL,
  embedding VECTOR(1536) NOT NULL,
  created_at TIMESTAMP NOT NULL
);
```

**③ 유사도 결과 캐시** — `game_similarities_weekly` 자체가 캐시 역할
- 두 게임 모두 feature_version 안 바뀌었으면 **지난 주 점수 복사**
- 한쪽이라도 바뀌었으면 재계산

**무효화 규칙 (delta-only 재계산)**:
```
games.updated_at 변경
  → 해당 게임 feature 재추출 (llm_cache hit이면 비용 0)
  → 해당 게임 embedding 재생성
  → 해당 게임이 연루된 similarity pair만 재계산
  → 나머진 전주 결과 복사
```
이 룰로 매주 전체 재계산 아닌 **delta만** 처리 → PoC 주간 비용 수천원 단위로 유지 가능.

---

## 핵심 파일 (구현 시)

- `collectors/steam.py`, `collectors/playstore.py`
- `pipeline/normalize.py`
- `pipeline/feature_extractor.py` (LLM 호출)
- `pipeline/embedder.py` (OpenAI/Claude embedding)
- `engine/similarity.py`
- `engine/weight_tuner.py` (grid search)
- `report/weekly.py`
- `schema.sql`

---

## Verification

1. **Unit**: feature_extractor 출력이 schema 일치, canary 정답률 측정
2. **Integration**: 10개 게임으로 end-to-end 파이프라인 돌려 `game_similarities_weekly` 채워지는지
3. **Quality**: gold set 20개로 precision@10 측정, 목표 ≥ 0.6
4. **E2E**: 실제 200개 게임 대상 1회 주간 실행 → Slack 리포트 도달 확인
5. **Feedback loop**: 리포트에 upvote 누르면 `pm_feedback` 테이블에 row 들어오는지
