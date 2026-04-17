# 진행 상황 및 남은 작업

**마지막 업데이트**: 2026-04-18

세션별 상세 변경: `docs/progress-2026-04-18.md`

---

## 완료된 작업

### Week 1 — 수집 + 스키마 ✅

- Postgres(pgvector) 컨테이너 기동 (`gca-pg`, 포트 55432 / WSL2 기반)
- `schema.sql` 13개 테이블 적용 + `is_my_game` 컬럼 추가 (2026-04-18)
- Steam 수집: 10 games + 1,000 reviews (현재 DB 상태)
- 정규화: 10 games

### Week 2 — 완료 ✅

- 임베딩: sentence-transformers `all-MiniLM-L6-v2`, 384차원 (로컬)
- **Feature 추출**: Claude → Groq 전환 완료 (`llama-3.3-70b-versatile`, OpenAI-compatible API)

### Week 3 — 완료 ✅

- Weak labels (tag_overlap, Steam morelike)
- 유사도 계산 (`is_my_game` 필터 적용 후 9 rows)
- 가중치 튜닝 (PM feedback + weak label 기반)

### Week 4 — 완료 ✅

- 주간 리포트 생성 (Groq 요약 + Jinja2 템플릿)
- FastAPI `serve` 정상 동작

### 추가 — 내부 PM 툴 완성 (2026-04-18) ✅

- `is_my_game` 플래그 + `gca add-my-game` CLI
- Next.js 16 FE 3페이지 (내 게임 / 경쟁작 / 리포트)
- Vercel 배포 준비 (`api/index.py` + lean `requirements.txt`)
- Terraform IaC (Supabase + Vercel 모듈)

---

## 해결된 블로커

### ❌ → ✅ `ANTHROPIC_API_KEY` 결제 불가

- **해결**: Groq API로 전환 (OpenAI-compatible, 무료 tier 충분)
- `pyproject.toml`: `anthropic` 제거, `openai>=1.50` 유지
- `config.py`: `groq_api_key` + `llm_model = "llama-3.3-70b-versatile"`
- `.env.example`: `GROQ_API_KEY=`로 교체
- 영향 파일: `feature_extractor.py`, `report/weekly.py` — `OpenAI(base_url="https://api.groq.com/openai/v1")` 사용

### ❌ → ✅ Docker Desktop virtualisation 오류

- BIOS 가상화는 켜져 있으나 Hyper-V feature OFF + WSL 미설치
- **해결**: `wsl --install` + `dism /enable-feature Microsoft-Hyper-V` + 재부팅

### ❌ → ✅ Windows cp949 인코딩 오류

- `sql_path.read_text()` → `read_text(encoding="utf-8")` (cli.py)
- `PYTHONIOENCODING=utf-8` 환경변수로 체크마크(`✓`) 출력 해결

### ❌ → ✅ pgvector 임베딩 문자열 반환

- psycopg3가 `vector` 타입을 문자열로 반환 → similarity에서 float 변환 실패
- **해결**: `db.py`에 `from pgvector.psycopg import register_vector` + `register_vector(conn)` 추가

---

## DB 현황 (2026-04-18 기준)

| 테이블 | 건수 |
|---|---|
| `raw_games` | 10 |
| `raw_reviews` | 1,000 |
| `games` | 10 (그중 `is_my_game = TRUE` 1건: New World: Aeternum) |
| `game_embeddings` | 10 |
| `game_features` | 10 |
| `game_similarities_weekly` | 9 (base_game_id=1, week 2026-04-13) |
| `weekly_reports` | 1 |
| `pm_feedback` | 0 |

---

## 인프라 상태

- **gca-pg**: `pgvector/pgvector:pg16`, port 55432, WSL2 backend
- **Python venv**: sentence-transformers + torch + groq-compatible openai SDK
- **Next.js web**: Next 16.2.4 + React 19 + Tailwind v4 + turbopack
- **Vercel 배포 준비**: `vercel.json` + `api/` + `web/`
- **Terraform**: `infra/terraform/` (apply 대기 중 — 토큰 입력 후 실행)

---

## 남은 작업 (범위 밖 / 후속)

- 인증·권한 (Vercel password protection으로 프로토 단계 회피 가능)
- batch 파이프라인 자동화 (GitHub Actions cron)
- `add-my-game` Play Store / App Store 확장
- PM 피드백 실데이터 수집 → `tune-weights` 재실행
- `POST /reports/generate`의 serverless-친화적 경로 (현재는 로컬/cron에서만 가능)
