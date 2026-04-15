# Plan Implementation Status

원본 기획: `docs/plan.md`
대화 내역: `docs/conversation.md`

**마지막 업데이트**: 2026-04-15 (전체 코드 구현 완료 — 환경 세팅만 남음)

---

## 요약

| Week | 목표 | 상태 |
|---|---|---|
| **Week 1** | 수집 + 스키마 + 정규화 | 🟢 코드 완료, DB 실행만 남음 |
| **Week 2** | Feature 추출 (LLM) + 임베딩 | 🟢 코드 완료 |
| **Week 3** | 유사도 엔진 + 가중치 튜닝 | 🟢 코드 완료 |
| **Week 4** | 리포트 + FastAPI + 피드백 루프 | 🟢 코드 완료 |

> DB + Python 환경만 세팅하면 end-to-end 동작 가능

---

## ✅ 전체 구현 완료 파일

### 프로젝트 인프라
- `pyproject.toml`, `conftest.py`, `.env.example`, `README.md`, `.gitignore`

### 스키마 (`schema.sql`) — 12개 테이블
| 테이블 | 용도 |
|---|---|
| `raw_games`, `raw_reviews` | 원본 보존 |
| `games` | 정규화 레이어 |
| `game_features` | SCD Type 2 feature store |
| `game_embeddings` | pgvector 1536 |
| `game_similarities_weekly` | 주간 유사도 스냅샷 |
| `pm_feedback` | PM upvote/downvote signal |
| `llm_cache`, `embedding_cache` | 비용 절감 캐시 |
| `pipeline_runs` | 관측성 |
| `weekly_reports` | 생성된 리포트 |
| `weight_history` | 튜닝된 가중치 이력 |
| `weak_similarities` | 플랫폼 similar signal |

### 수집 (`src/gca/collectors/`)
| 파일 | 상태 | 비고 |
|---|---|---|
| `base.py` | ✅ | Collector Protocol |
| `steam.py` | ✅ | SteamSpy + Steam API, tenacity retry, live test 완료 |
| `appstore.py` | ✅ | iTunes Search API, 공식 공개 |
| `playstore.py` | 🟡 stub | google-play-scraper optional dep |
| `itch.py` | ✅ | itch.io 공개 API |

### 파이프라인 (`src/gca/pipeline/`)
| 파일 | 용도 |
|---|---|
| `runs.py` | 파이프라인 추적 context manager |
| `normalize.py` | raw → games UPSERT (Steam/PlayStore/AppStore) |
| `cache.py` | llm_cache + embedding_cache DB helper |
| `feature_prompt.py` | Claude 프롬프트 템플릿 + canary 질문 |
| `feature_extractor.py` | Claude API → game_features (SCD Type 2) |
| `embedder.py` | OpenAI text-embedding-3-small → game_embeddings |

### 엔진 (`src/gca/engine/`)
| 파일 | 용도 |
|---|---|
| `features.py` | Feature Store API (point-in-time lookup) |
| `similarity.py` | 4축 유사도 공식 + 주간 배치 계산 |
| `weight_tuner.py` | NDCG@10 기준 grid search, weight_history 저장 |
| `weak_labels.py` | Steam morelike + tag_overlap weak label 수집 |

### 리포트 (`src/gca/report/`)
| 파일 | 용도 |
|---|---|
| `weekly.py` | 리포트 생성/렌더링/저장 |
| `templates/weekly.md.j2` | Jinja2 Markdown 템플릿 |

### API (`src/gca/api/`)
| 파일 | 엔드포인트 |
|---|---|
| `server.py` | FastAPI app + CORS |
| `routes/competitors.py` | `GET /games`, `GET /competitors` |
| `routes/feedback.py` | `POST /feedback`, `GET /feedback/summary` |
| `routes/reports.py` | `GET /reports`, `POST /reports/generate` |

### 핵심 모듈
- `config.py`, `db.py`, `logs.py`, `models.py`

### CLI (`src/gca/cli.py`) — 14개 서브커맨드
```
migrate              DB 스키마 적용
collect:steam        Steam 수집
collect:appstore     App Store 수집
collect:itch         itch.io 수집
normalize            raw → games 정규화
extract-features     Claude LLM feature 추출
embed                OpenAI 임베딩 생성
feature-quality      gold set 대비 accuracy 측정
weak-labels          weak similarity label 수집
similarity           4축 유사도 계산 + DB 저장
tune-weights         가중치 grid search 튜닝
report               주간 리포트 생성
serve                FastAPI 서버 실행
status               파이프라인 상태 조회
```

### 테스트
- `tests/test_normalize.py` — 6개 (기존)
- `tests/fixtures/gold_features.yaml` — 20개 PM 라벨 gold set

---

## 🔴 환경 세팅 (코드 실행에 필요)

### 1. Python + 패키지 설치
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Postgres + pgvector 기동
```bash
docker run -d --name gca-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=game_competitor \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 3. `.env` 생성
```bash
cp .env.example .env
# ANTHROPIC_API_KEY, OPENAI_API_KEY, STEAM_API_KEY 설정
```

### 4. End-to-end 파이프라인 실행
```bash
# Week 1
python -m gca.cli migrate
python -m gca.cli collect:steam --limit 200 --fetch-reviews
python -m gca.cli collect:appstore --limit 200
python -m gca.cli collect:itch --limit 100
python -m gca.cli normalize
python -m gca.cli status

# Week 2
python -m gca.cli extract-features --changed-only
python -m gca.cli embed --changed-only
python -m gca.cli feature-quality

# Week 3
python -m gca.cli weak-labels --source tag_overlap
python -m gca.cli weak-labels --source steam
python -m gca.cli tune-weights
python -m gca.cli similarity --week-of $(date +%Y-%m-%d)

# Week 4
python -m gca.cli report --week-of $(date +%Y-%m-%d)
python -m gca.cli serve
```

---

## 유사도 공식

```python
score = (
    w_semantic * cosine(desc_embed_a, desc_embed_b)   # 0.40
  + w_genre    * cosine(genre_embed_a, genre_embed_b)  # 0.25
  + w_tier     * exp(-|tier_a - tier_b| / 0.3)         # 0.20
  + w_bm       * (1 - KL_symmetric(bm_dist_a, bm_dist_b))  # 0.15
)
```

가중치는 `tune-weights`로 PM feedback + weak label 기반 grid search 자동 튜닝.

---

## 주요 설계 결정

| 결정 | 내용 |
|---|---|
| 프레임 | 경쟁작 분석 도구 ❌ → 리서치팀 반복업무 자동화 ✅ |
| 성공 지표 | precision@N 아닌 "PM 리포트 준비 시간 X→Y" |
| 경쟁작 정의 | Target user overlap이 북극성. PoC는 4축 연속값 유사도로 근사 |
| Ground truth | PM 라벨 20개 gold set + 플랫폼 similar signal (weak label) |
| HITL | 검수 단계 제거. upvote/downvote 암묵적 signal만 |
| Feature Store | Postgres + pgvector + 얇은 Python API (Feast X) |
| 캐싱 | LLM + embedding + similarity 3단계, delta-only 재계산 |
| API | read-only except POST /feedback |
| 오케스트레이션 | Cron + Python (PoC) → Prefect (확장) |
