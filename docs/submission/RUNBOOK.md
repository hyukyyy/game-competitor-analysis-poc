# 과제전형 제출 Runbook

> 지원자: 윤동혁 · 포지션: AI 애플리케이션 엔지니어 · 마감: 2026-04-21 23:59
>
> 이 문서는 **제출 전 남은 작업**을 순서대로 실행하기 위한 체크리스트입니다.
> 각 단계는 **이 문서의 번호 순서대로** 진행하세요.

---

## 0. 사전 준비

필요한 계정 · 토큰 5종:

| 항목 | 발급 위치 | 비고 |
|---|---|---|
| Supabase Access Token | https://supabase.com/dashboard/account/tokens | `sbp_...` 로 시작 |
| Supabase Org ID | https://supabase.com/dashboard/orgs → 선택 후 URL 의 UUID | 예: `abcd-1234-...` |
| Supabase DB Password | 신규 생성 (강력한 문자열) | Terraform 이 프로젝트 생성 시 사용 |
| Vercel API Token | https://vercel.com/account/tokens | Full Access scope |
| Groq API Key | 이미 `.env` 에 있음 | `gsk_...` 로 시작 |

**이미 확보된 것**: GitHub repo (`hyukyyy/game-competitor-analysis-poc`), Groq API key.

**필요한 로컬 도구**: `terraform >= 1.5`, `psql` (Supabase 스키마 적용용), `git`.

---

## 1. GitHub 에 최신 코드 푸시

로컬에 커밋되지 않은 변경이 있습니다 — 제출 산출물 디렉토리 `docs/submission/` 과 빌드 스크립트.

```bash
git add docs/submission/ scripts/build_submission_deck.py
git commit -m "docs: add 과제전형 submission package"
git push origin main
```

> 반드시 `main` 브랜치에 푸시해야 Terraform 의 Vercel 프로바이더가 production branch = main 으로 배포합니다.

---

## 2. Terraform tfvars 작성

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

`infra/terraform/terraform.tfvars` 를 열어 다음 값을 실제 값으로 교체:

```hcl
project_name         = "gca"

supabase_access_token = "sbp_REAL_TOKEN_HERE"
supabase_org_id       = "YOUR_ORG_UUID"
supabase_region       = "ap-northeast-2"
supabase_db_password  = "STRONG_PASSWORD_HERE"

vercel_api_token  = "REAL_VERCEL_TOKEN_HERE"
vercel_team_id    = null                              # 개인 계정이면 null 유지
github_repo       = "hyukyyy/game-competitor-analysis-poc"
production_branch = "main"

groq_api_key = "gsk_REAL_GROQ_KEY_HERE"
llm_model    = "llama-3.3-70b-versatile"
```

> `terraform.tfvars` 는 `.gitignore` 에 포함되어 있어 commit 되지 않습니다.

---

## 3. Terraform Apply

```bash
cd infra/terraform
terraform init
terraform plan       # 검토
terraform apply      # yes 입력
```

약 3–5 분 소요 (Supabase 프로젝트 프로비저닝이 가장 오래 걸림). 완료 시 **Outputs** 에:

```
api_url = "https://gca-api.vercel.app"
web_url = "https://gca-web.vercel.app"
```

### 자주 발생하는 이슈

- **`psql: command not found`** — `psql` 설치 필요. Windows: `winget install PostgreSQL.PostgreSQL` 또는 Chocolatey.
- **Supabase org 당 프로젝트 2개 초과** — 기존 미사용 프로젝트 삭제 후 재시도.
- **Vercel "project exists"** — Vercel 대시보드에서 동명 프로젝트 삭제 후 재시도.
- **첫 Vercel 배포가 commit 을 필요로 함** — `git push` 전에 terraform apply 하면 production deployment 가 없을 수 있음. push 를 먼저 했다면 문제 없음.

---

## 4. 프로토타입 동작 확인

배포 후 **최소 1번의 배치 실행**이 필요합니다 (DB 가 비어 있으므로):

```bash
# 로컬에서 Supabase 에 접속해 배치 실행
# .env 의 DATABASE_URL 을 Supabase 로 교체
export DATABASE_URL="postgresql://postgres:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres?sslmode=require"
export GROQ_API_KEY="gsk_..."

.venv/Scripts/gca collect:steam --limit 50 --fetch-reviews
.venv/Scripts/gca normalize
.venv/Scripts/gca extract-features --changed-only
.venv/Scripts/gca embed
.venv/Scripts/gca add-my-game --platform steam --appid 730           # CS2
.venv/Scripts/gca similarity --week 2026-W16
.venv/Scripts/gca report --week 2026-W16
```

> `collect:steam --limit 50` 으로 제한하면 10분 이내 완료. 전체 200 개는 30분+ 소요.

브라우저에서 확인:

- `https://gca-web.vercel.app/` → My Games 카드에 CS2 가 보임
- `https://gca-web.vercel.app/games/1` → 경쟁작 Top 10 (ID 는 DB 에 따라 1 또는 다른 값)
- `https://gca-web.vercel.app/games/1/report` → 주간 리포트 markdown

---

## 5. 데모 GIF 녹화 (60초 시나리오)

### 도구 (Windows)

**추천**: [ScreenToGif](https://www.screentogif.com/) (무료 · 직접 GIF export · 편집 가능) 또는 [ShareX](https://getsharex.com/) (무료 · 범용).

### 시나리오 (총 60초)

| 시간 | 동작 |
|---|---|
| 00:00–00:08 | `https://gca-web.vercel.app/` 로드 · 헤더 + "My Games" 영역 보이기 |
| 00:08–00:20 | AddMyGameForm 에 `730` 입력 → Submit → 내 게임 카드 추가 (이미 추가돼 있으면 다른 appid 사용) |
| 00:20–00:35 | 내 게임 카드 클릭 → `/games/[id]` · 경쟁작 Top 10 · **4축 component score bar** 를 스크롤하며 보여주기 |
| 00:35–00:42 | 상위 경쟁작에 👍 클릭 → 토스트/상태 변경 확인 |
| 00:42–00:55 | 우상단 "Weekly Report" 버튼 클릭 → `/games/[id]/report` · 마크다운 리포트 섹션 스크롤 |
| 00:55–01:00 | 우상단 "Download PDF" 클릭 → 브라우저 인쇄 창 열림 |

### 녹화 세팅

- 창 크기: **가로 1000~1200px, 세로 700~800px** (넓으면 GIF 용량 증가)
- 프레임레이트: **15fps** (30fps 는 용량 2배, 효과 미미)
- 색 깊이: GIF 기본값 (256 color)
- 목표 용량: **< 10MB**

### 저장

- 파일명: `docs/submission/demo.gif`
- 녹화 후 파일 크기 확인. 10MB 초과 시 ScreenToGif "Reduce frame count" 로 압축.

---

## 6. 프로토타입 URL · GIF 경로 주입 + 재빌드

녹화와 배포가 모두 끝난 시점의 실제 값으로 업데이트:

**편집 파일**: [scripts/build_submission_deck.py](../../scripts/build_submission_deck.py)

```python
PROTOTYPE_WEB_URL = "https://gca-web.vercel.app"   # 실제 URL 확인 후 수정
PROTOTYPE_API_URL = "https://gca-api.vercel.app"   # 실제 URL 확인 후 수정
DEMO_GIF_URL = "docs/submission/demo.gif"           # 경로 유지 or 외부 링크
```

재빌드:

```bash
.venv/Scripts/python scripts/build_submission_deck.py
```

→ `docs/submission/submission.pptx` 갱신 확인.

---

## 7. PDF Export

### 옵션 A — PowerPoint 에서 (권장)

1. `docs/submission/submission.pptx` 를 PowerPoint 에서 열기
2. **파일 → 내보내기 → PDF/XPS 만들기**
3. "최소 크기" 가 아닌 **"표준 (온라인 게시 및 인쇄)"** 선택
4. 저장 경로: `docs/submission/윤동혁_AI 애플리케이션 엔지니어_과제전형.pdf`

### 옵션 B — LibreOffice headless (자동화)

LibreOffice 가 설치돼 있다면:

```bash
cd docs/submission
soffice --headless --convert-to pdf submission.pptx
# → submission.pdf 생성됨
mv submission.pdf "윤동혁_AI 애플리케이션 엔지니어_과제전형.pdf"
```

### 품질 체크

- 20개 슬라이드 모두 포함
- Cover · 요약 · 6개 섹션 ①~⑥ · 프로토타입 · 와이어프레임 3장 · 데모 시나리오 · 부록 · Thank you
- 한글 폰트 깨짐 없음 (Calibri 대체 된 경우도 있으니 실제 확인)
- 와이어프레임 박스/라벨 잘림 없음
- 하이퍼링크는 PDF 에서 클릭 가능해야 함 (PowerPoint export 시 기본 동작)

---

## 8. 제출 파일 최종 체크리스트

제출 디렉토리 상태:

```
docs/submission/
├── 윤동혁_AI 애플리케이션 엔지니어_과제전형.pdf   ← 메인 제출물
├── submission.pptx                                ← PDF 원본 (백업)
├── demo.gif                                       ← 별도 첨부 가능
├── vibe-coding-prompts.md                         ← 별도 첨부 가능
└── RUNBOOK.md                                     ← 이 파일 (제출 X)
```

제출 전 최종 확인:

- [ ] PDF 파일명이 정확: `윤동혁_AI 애플리케이션 엔지니어_과제전형.pdf`
- [ ] PDF 안에 6개 섹션 ①~⑥ 번호가 명시됨
- [ ] 프로토타입 URL 이 placeholder (`gca-web.vercel.app`) 가 아닌 **실제 배포 URL** 로 업데이트됨
- [ ] 프로토타입 URL 을 시크릿 창에서 열어 실제 동작 확인
- [ ] `/`, `/games/[id]`, `/games/[id]/report` 3개 라우트 모두 응답
- [ ] demo.gif 재생 시 5단계 플로우가 모두 보임
- [ ] GIF 용량 < 10MB
- [ ] vibe-coding-prompts.md 에 역할·기능·UI·기술 스택 4요소 모두 포함됨 (이미 확인)
- [ ] **제출 마감 2시간 전 (2026-04-21 21:59 전)** 에 업로드 완료 예정

---

## 9. 제출

제출 채널(이메일/폼)에:

1. **본문 PDF**: `윤동혁_AI 애플리케이션 엔지니어_과제전형.pdf`
2. **프로토타입 링크** (PDF 에도 있지만 본문에도 적어주기)
3. **데모 GIF**: `demo.gif` (PDF 내 링크로 충분하지 않다면 별도 첨부)
4. **바이브코딩 지시**: PDF 섹션 ⑥ + (요청 시) `vibe-coding-prompts.md` 별첨
5. **화면 설계**: PDF 내 와이어프레임 3장

제출 완료 후 이메일 수신/폼 제출 확인 스크린샷을 남겨두세요.

---

## 비상 대응

| 상황 | 대응 |
|---|---|
| Terraform apply 실패 | 수동 배포로 전환 — Vercel/Supabase 대시보드에서 직접 생성 후 env var 설정 |
| GIF 용량 초과 | 프레임레이트 10fps 로 낮추거나 해상도 800px 로 축소 |
| PDF 한글 폰트 깨짐 | PowerPoint 에서 수동으로 Calibri → "맑은 고딕" 으로 일괄 치환 |
| 프로토타입이 Supabase 콜드 스타트로 느림 | 제출 직전 브라우저로 1회 접속 → warmup |
| Groq 무료 tier rate limit | 배치는 캐시되므로 재실행 시 문제 없음. FE 리포트 요청은 DB 에서만 fetch — 런타임 LLM 호출 없음 |
