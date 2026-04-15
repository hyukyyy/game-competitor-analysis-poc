# Game Competitor Analysis — PoC

게임 회사 리서치팀의 반복 업무(주간 경쟁작 리서치 & 리포트 작성) 자동화 PoC.

상세 기획: [`/home/dyoon/.claude/plans/shimmying-chasing-plum.md`](../../../.claude/plans/shimmying-chasing-plum.md)
대화 내역: [`docs/conversation.md`](docs/conversation.md)

## Stack

- Python 3.11+
- PostgreSQL 15+ with `pgvector`
- httpx, psycopg, pydantic-settings
- (Week 2+) Anthropic / OpenAI embeddings

## Setup

```bash
# 1) create venv & install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2) env
cp .env.example .env
# edit .env — set DATABASE_URL at minimum

# 3) start postgres (example via docker)
docker run -d --name gca-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=game_competitor \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# 4) migrate
python -m gca.cli migrate
```

## Week 1 — 수집 + 정규화

```bash
# Steam top 200 수집
python -m gca.cli collect:steam --limit 200

# 정규화 (raw_games → games)
python -m gca.cli normalize

# 상태 확인
python -m gca.cli status
```

## 구조

```
src/gca/
├── config.py          # pydantic-settings
├── db.py              # psycopg connection
├── logs.py            # logger
├── models.py          # Pydantic DTO
├── cli.py             # CLI entrypoint
├── collectors/        # Platform collectors
│   ├── base.py
│   ├── steam.py       # Steam Web API (httpx) — Week 1 real impl
│   └── playstore.py   # stub (google-play-scraper, Week 1 후반)
├── pipeline/
│   ├── runs.py        # pipeline_runs tracker
│   └── normalize.py   # raw → normalized
├── engine/            # Week 3
└── report/            # Week 4

schema.sql             # DDL
migrations/            # (future)
tests/
docs/
```

## 4주 로드맵

| Week | 목표 | 상태 |
|---|---|---|
| 1 | 수집 + 스키마 + 정규화 | 🟡 진행 중 |
| 2 | Feature 추출 (LLM) + 임베딩 | ⚪ |
| 3 | 유사도 엔진 + 가중치 튜닝 | ⚪ |
| 4 | 리포트 생성 + 피드백 루프 | ⚪ |
