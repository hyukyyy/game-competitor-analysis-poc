# 진행 상황 및 남은 작업

**마지막 업데이트**: 2026-04-16

---

## 완료된 작업

### Week 1 — 수집 + 스키마 ✅
- [x] Postgres(pgvector) 컨테이너 기동 (`gca-pg`, 포트 55432)
- [x] `schema.sql` 13개 테이블 적용
- [x] Steam 수집: 100 games + 5,000 reviews
- [x] 정규화: 100 games

### Week 2 — 부분 완료
- [x] 임베딩: 100 games (sentence-transformers `all-MiniLM-L6-v2`, 384차원, 로컬)
- [ ] ❌ Feature 추출 — **BLOCKED** (아래 블로커 참고)
- [ ] Feature 품질 측정 — feature 추출 의존

---

## 블로커

### `ANTHROPIC_API_KEY` 인증 실패
- `extract-features` 실행 시 `401 authentication_error: invalid x-api-key`
- `.env`에 입력된 키가 OAuth Access Token (`sk-ant-oat01-...`) 형식
- 필요한 것: API Key (`sk-ant-api03-...`) — https://console.anthropic.com/settings/keys 에서 발급

---

## 남은 작업

### Week 2 (블로커 해소 후)
```bash
python -m gca.cli extract-features --changed-only   # Claude API
python -m gca.cli feature-quality                     # gold set 대비 측정
```

### Week 3 — 유사도 엔진 + 튜닝
```bash
python -m gca.cli weak-labels --source tag_overlap
python -m gca.cli weak-labels --source steam
python -m gca.cli tune-weights
python -m gca.cli similarity --week-of $(date +%Y-%m-%d)
```

### Week 4 — 리포트 + 피드백 루프
```bash
python -m gca.cli report --week-of $(date +%Y-%m-%d)
python -m gca.cli serve
```

---

## 이번 세션에서 수행한 코드 변경

| 파일 | 변경 내용 |
|---|---|
| `pyproject.toml` | `jinja2>=3.1` 추가, `openai>=1.50` → `sentence-transformers>=3.0` |
| `src/gca/config.py` | `openai_api_key` 제거, `embedding_model` 기본값 `all-MiniLM-L6-v2` |
| `src/gca/pipeline/embedder.py` | OpenAI client → SentenceTransformer 로컬 모델 |
| `schema.sql` | `vector(1536)` → `vector(384)` (3곳) |
| `.env.example` | `OPENAI_API_KEY` 제거, `EMBEDDING_MODEL=all-MiniLM-L6-v2` |

---

## DB 현황 (2026-04-16 기준)

| 테이블 | 건수 |
|---|---|
| `raw_games` | 100 |
| `raw_reviews` | 5,000 |
| `games` | 100 |
| `game_embeddings` | 100 |
| `game_features` | 0 (블로커) |
| `game_similarities_weekly` | 0 |
| `pm_feedback` | 0 |
| `weekly_reports` | 0 |

---

## 인프라 상태

- **gca-pg**: `docker ps` → port 55432, pgvector 0.8.2
- **Python venv**: `.venv/` with sentence-transformers 5.4.1 + torch 2.11.0
- **기존 Supabase 스택** (`on-boarding`): port 54321~54327, 별도 격리됨
