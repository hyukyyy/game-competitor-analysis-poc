# 개발 · 운영 명령어 가이드

> 작성일: 2026-04-18 · 기준: commit `5e6370f` · 대상 독자: 개발자 · 운영자

## 1. 사전 조건 (Prerequisites)

| 항목 | 버전 | 확인 |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node | 18+ (권장 20+) | `node --version` |
| Docker Desktop | 최신 (WSL2 backend) | `docker --version` |
| Groq API key | 무료 tier 충분 | https://console.groq.com |
| Terraform (IaC 적용 시) | 1.6+ | `terraform -version` |
| (선택) Steam Web API key | 수집 품질 향상용 | https://steamcommunity.com/dev |

---

## 2. 최초 셋업

```bash
# 1) Python 가상환경 + 패키지
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash). macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# 2) Postgres + pgvector (WSL2 필요)
docker run -d --name gca-pg \
  -e POSTGRES_PASSWORD=postgres \
  -p 55432:5432 \
  pgvector/pgvector:pg16

# 3) 환경 변수
cp .env.example .env
# .env 편집:
#   DATABASE_URL=postgresql://postgres:postgres@localhost:55432/postgres
#   GROQ_API_KEY=gsk_...
#   LLM_MODEL=llama-3.3-70b-versatile

# 4) 스키마 적용
gca migrate
# → ✓ migrations applied from schema.sql (13 tables + is_my_game + pgvector)
```

> **Windows 한글 출력 주의**: 모든 `gca` 명령 앞에 `PYTHONIOENCODING=utf-8` 를 붙이면 체크마크(✓) 가 깨지지 않는다. 아래 예시들에선 지면상 생략.

---

## 3. CLI 명령어 레퍼런스

모든 서브커맨드는 [src/gca/cli.py](../src/gca/cli.py) 에서 정의된다. `gca --help` 또는 `gca <cmd> --help` 로 실제 플래그 확인 가능.

### 3.1 `gca migrate`
- **하는 일**: `schema.sql` 을 현재 `DATABASE_URL` 에 적용 (idempotent)
- **쓰기**: 13개 테이블 + 인덱스 + `vector` extension
- **플래그**: `--schema <path>` (기본 `schema.sql`)
- **소요**: < 1s

### 3.2 `gca collect:steam`
- **하는 일**: SteamSpy top N appid → Steam Store API 상세 수집 → (옵션) 리뷰 수집
- **쓰기**: `raw_games`, `raw_reviews`, `pipeline_runs`
- **자주 쓰는 플래그**:
  ```bash
  gca collect:steam --limit 200 --fetch-reviews --review-limit 50
  ```
- **소요**: 200개 + 리뷰 50개 기준 ≈ 5~10 분 (레이트리밋)

### 3.3 `gca collect:appstore`
- **하는 일**: iTunes Search API 로 App Store 상위 게임 수집
- **쓰기**: `raw_games`, `raw_reviews`
- **플래그**: `--limit 200 --country us --fetch-reviews`
- **소요**: 100~200개 ≈ 2~5 분

### 3.4 `gca collect:itch`
- **하는 일**: itch.io 공개 API 로 top 게임 메타 수집 (리뷰 없음)
- **쓰기**: `raw_games`
- **플래그**: `--limit 200`
- **소요**: < 1 분

### 3.5 `gca normalize`
- **하는 일**: `raw_games.payload` → 정규화 스키마 (`games.title/description/raw_tags`)
- **읽기**: `raw_games` / **쓰기**: `games`
- **소요**: < 10s (200개 기준)

### 3.6 `gca extract-features`
- **하는 일**: `games` 의 title + description + reviews → Groq `llama-3.3-70b-versatile` 로 feature 추출 → `game_features` SCD Type 2 적재
- **읽기**: `games`, `raw_reviews`, `llm_cache` / **쓰기**: `game_features`, `llm_cache`
- **플래그**: `--changed-only` (현재 valid row 없는 게임만)
- **소요**: 캐시 히트율에 따라 게임당 1~3s

### 3.7 `gca embed`
- **하는 일**: description + reviews → `all-MiniLM-L6-v2` 로 임베딩 (384d, **로컬 연산** — API 호출 없음)
- **읽기**: `games`, `raw_reviews`, `embedding_cache` / **쓰기**: `game_embeddings`, `embedding_cache`
- **플래그**: `--changed-only`
- **소요**: 200개 ≈ 30s~1분 (CPU), GPU 있으면 더 빠름

### 3.8 `gca feature-quality`
- **하는 일**: `tests/fixtures/gold_features.yaml` 과 LLM 출력 field-wise 비교 → accuracy % + canary 정답률 출력
- **플래그**: `--fixture <path>`
- **소요**: gold set 20개 ≈ 30s

### 3.9 `gca weak-labels`
- **하는 일**: weak similarity label 수집 (Steam "More Like This" 또는 tag overlap)
- **쓰기**: `weak_similarities`
- **플래그**: `--source {tag_overlap,steam} --min-shared 3`
- **소요**: < 1분

### 3.10 `gca tune-weights`
- **하는 일**: `pm_feedback` + `weak_similarities` 로 grid search → 최적 가중치
- **쓰기**: `weight_history`
- **플래그**: `--n-steps 5 --k 10` (grid 해상도 / NDCG@k)
- **소요**: n_steps=5 기준 수십 초

### 3.11 `gca similarity`
- **하는 일**: `is_my_game = TRUE` 게임을 base 로 Top N 경쟁작 계산
- **읽기**: `game_features`, `game_embeddings`, `games.is_my_game`, `weight_history` / **쓰기**: `game_similarities_weekly`
- **플래그**: `--week-of <YYYY-MM-DD> --top-n 20 --changed-only --default-weights`
- **소요**: my_game 1개 × 200 candidate ≈ 수 초
- **주의**: `is_my_game = TRUE` 게임이 없으면 0 row 기록 + 경고. `gca add-my-game` 먼저 실행

### 3.12 `gca report`
- **하는 일**: `game_similarities_weekly` + Groq 요약 → Jinja2 Markdown 렌더 → `weekly_reports` 저장 (+ `--game-id` 사용 시 파일로도 dump)
- **읽기**: similarities, games, `games.is_my_game` / **쓰기**: `weekly_reports`, `pipeline_runs`
- **플래그**: `--week-of --game-id <int> --top-n 10`
- **소요**: 게임당 수 초 (Groq 호출 포함)

### 3.13 `gca serve`
- **하는 일**: FastAPI 서버 기동 (`gca.api.server:app`)
- **플래그**: `--host 0.0.0.0 --port 8000 --reload`
- **소요**: 즉시

### 3.14 `gca status`
- **하는 일**: `raw_games`, `games`, 최근 `pipeline_runs` 10건 요약 출력
- **소요**: < 1s

### 3.15 `gca add-my-game` *(PM 툴 신규)*
- **하는 일**: Steam appid → `raw_games` 원본 저장 + `games.is_my_game = TRUE` upsert
- **쓰기**: `raw_games`, `games`
- **플래그**: `--platform steam --appid <id>` (현재 Steam 전용)
- **예시**:
  ```bash
  gca add-my-game --platform steam --appid 1063730
  # → ✓ registered my_game id=1 title='New World: Aeternum' (steam:1063730)
  ```
- **소요**: < 2s

---

## 4. 전체 주간 배치 실행 (복사 가능한 블록)

```bash
# Windows: 앞에 PYTHONIOENCODING=utf-8 각각 붙여도 됨 (한글 출력)
gca collect:steam --limit 200 --fetch-reviews
gca normalize
gca extract-features --changed-only
gca embed --changed-only
gca weak-labels --source tag_overlap
gca tune-weights
gca similarity
gca report
```

실행 순서 불변 — 앞 stage 가 실패하면 뒤 stage 는 데이터가 비어서 warning 만 찍힌다.
`gca status` 로 중간중간 진행 상태 확인 가능.

---

## 5. FE 개발 서버 (Next.js 16)

```bash
cd web
cp .env.local.example .env.local
# .env.local 편집:
#   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

npm install
npm run dev     # turbopack, http://localhost:3000
```

- Next.js 16 의 `params` / `searchParams` 는 **`Promise<{...}>`** 이다. 반드시 await.
- 세부 주의사항: [web/AGENTS.md](../web/AGENTS.md).

---

## 6. API 로컬 실행 + 스모크 테스트

```bash
# 백엔드 기동
gca serve --port 8000

# 다른 터미널:
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/games?mine=true"
curl "http://127.0.0.1:8000/competitors?base_game_id=1&limit=10"
curl "http://127.0.0.1:8000/reports?base_game_id=1&format=markdown"

# 피드백 write 경로
curl -X POST "http://127.0.0.1:8000/feedback" \
  -H "Content-Type: application/json" \
  -d '{"base_game_id":1,"target_game_id":2,"week_of":"2026-04-13","signal":"upvote"}'
```

API 전체 라우트: [src/gca/api/server.py](../src/gca/api/server.py). Swagger UI 는 `http://127.0.0.1:8000/docs`.

---

## 7. Terraform IaC 적용 (Supabase + Vercel)

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
# 다음 값 채우기:
#   supabase_access_token  (sbp_...)
#   supabase_org_id
#   supabase_db_password   (강한 패스워드)
#   vercel_api_token
#   github_repo            (예: "my-org/game-competitor-analysis-poc")
#   groq_api_key           (gsk_...)

cd infra/terraform
terraform init
terraform plan
terraform apply       # 약 3~5분: Supabase project 생성 + pgvector + schema.sql 적용
```

출력:

- `module.supabase.database_url` — Vercel 에 자동 주입됨
- `module.vercel.web_url` — `https://gca-web.vercel.app`
- `module.vercel.api_url` — `https://gca-api.vercel.app`

적용 후 GitHub repo 의 `main` 브랜치에 push 하면 Vercel 이 자동 빌드한다.
배치 파이프라인(`gca collect:steam` 등) 은 **로컬 또는 CI runner 에서 실행**해서 Supabase DB 에 write — Vercel serverless 에서는 ML deps 가 50MB 초과로 실행 불가.

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `UnicodeEncodeError: 'charmap' codec can't encode '✓'` | Windows 기본 stdout 이 cp949 | `set PYTHONIOENCODING=utf-8` 또는 명령 앞에 `PYTHONIOENCODING=utf-8 gca ...`. `cli.py` 는 이미 `read_text(encoding="utf-8")` 로 파일은 안전 |
| Docker Desktop "virtualisation not enabled" | BIOS VT-x 켜져있어도 Hyper-V/WSL 미설치 | `wsl --install` + `dism /online /enable-feature /featurename:Microsoft-Hyper-V /all` + 재부팅 |
| `similarity` 실행 시 `float() argument must be a string or real number, not 'str'` | psycopg3 가 pgvector 를 문자열로 반환 | 이미 [src/gca/db.py](../src/gca/db.py) 에 `register_vector(conn)` 적용됨. 변경 사항 pull 확인 |
| `feature_extractor` 401/403 | Anthropic 키 기대 (deprecated) | `.env` 에 `ANTHROPIC_API_KEY` 대신 `GROQ_API_KEY` 확인. 코드는 OpenAI-compatible Groq 엔드포인트 사용 |
| Vercel 빌드 시 "Function size exceeds 50MB" | `pyproject.toml` 의 sentence-transformers/torch 가 패킹됨 | Vercel 은 `api/requirements.txt` (lean) 만 사용. `vercel.json` 의 `includeFiles: src/**` 확인 |
| `gca similarity` 가 0 rows 기록 + "No games flagged is_my_game=TRUE" warning | base 게임 미등록 | `gca add-my-game --platform steam --appid <id>` 먼저 실행 |

---

## 9. Git 컨벤션

### 커밋 메시지 (현재 repo 스타일)

```
<type>: <한 줄 요약 (영문)>

<본문 — 무엇/왜. 한국어 OK>
```

`<type>` 예시:

- `feat:` 새 기능
- `fix:` 버그 수정
- `docs:` 문서만 변경
- `refactor:` 코드 정리 (동작 불변)
- `chore:` 설정/의존성 등 자잘한 변경

최근 커밋 참고:

```
5e6370f feat: add is_my_game flag, Next.js FE, and deployment IaC
320d323 fix: fix on bugs
7f3d48e feat: update cli function
```

### 브랜치

- `main` 이 프로덕션 (Vercel `production_branch`)
- 기능/실험은 별도 브랜치 후 PR → squash merge 권장

---

## 관련 문서

- [docs/service-architecture.md](./service-architecture.md) — 전체 구조 · DB 스키마 · 유사도 공식
- [docs/product-guide.md](./product-guide.md) — PM 사용 플로우
- [docs/not-done.md](./not-done.md) — 남은 작업 · 해결된 블로커
- [docs/progress-2026-04-18.md](./progress-2026-04-18.md) — 최근 세션 구현 상세
- [.env.example](../.env.example) — 필수 환경 변수
- [infra/terraform/terraform.tfvars.example](../infra/terraform/terraform.tfvars.example) — IaC 주입 변수
