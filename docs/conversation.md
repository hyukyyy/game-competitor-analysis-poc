# 게임 경쟁작 자동 분석 시스템 — 대화 내역

> 게임 회사 리서치팀의 반복 업무(주간 경쟁작 리서치 & 리포트 작성) 자동화 PoC를 설계하기 위한 사전 논의.
> 기간: 2026-04-15
> 결과물: `/home/dyoon/.claude/plans/shimmying-chasing-plum.md` (최종 기획서), 본 프로젝트 리포지토리.

---

## Turn 1 — 사용자: 초기 설계서 공유

게임 경쟁작 자동 분석 시스템 구현 설계서 (Prototype) 전문을 공유하고 "이거 분석해봐" 요청.

### 설계서 핵심 요약
- **목적**: 게임 시장 리서치 자동화 — 특정 게임 기준 경쟁작 Top N 자동 도출, 주간 리포트, 최소 Human 검수
- **범위**: 모바일(Play Store) + PC(Steam), Top 200개, 주간 배치
- **아키텍처**: Batch → Raw DB → Normalized DB → Analysis(LLM) → Feature Store → Similarity Engine → Result DB → API → FE
- **Feature 정의**: genre, subgenre, bm (gacha/ads/premium), play_style, session_length, core_loop
- **유사도 공식**: `genre_match*0.4 + bm_match*0.2 + play_style_similarity*0.2 + session_length_match*0.1 + 기타*0.1`
- **일정**: 4주 (DB 설계 → Feature 추출 → 유사도 → 리포트)
- **리스크**: Feature 정확도, 데이터 부족, 조직 신뢰 부족

---

## Turn 2 — Assistant: 설계서 비판

### 🔴 Critical (설계의 논리적 결함)

1. **유사도 공식 자기모순**: `genre_match*0.4`인데 "동일 장르만 비교" 최적화 적용 시 항상 1 → 가중치 40%가 죽음
2. **"기타 * 0.1"의 정의 없음**: 핵심 공식에 미정의 항목
3. **카테고리 매칭(0/1)만으로 변별력 없음**: 이진 매칭이면 수십 개가 동점. 임베딩 기반 연속 유사도가 왜 없는지 의문
4. **"경쟁작" 정의 자체 모호**: 장르+BM 유사 ≠ 경쟁작. 규모, 타겟 유저층, 지역, 직접 vs 대체재 구분 빠짐

### 🟠 Major

5. 주간 "순위 변동" 계산 불가 (스냅샷 버전 없음)
6. Feature 추출 품질 측정 장치 없음 (drift, consistency, gold truth)
7. HITL이 루프가 아님 (검수 결과가 모델에 feedback 안 됨)
8. 성능 걱정 방향 반대 (200×200=4만 pair면 연산 문제 아님. 오히려 N 작음)
9. 크롤링 법적 리스크 (Play Store/Steam ToS)

### 🟡 Minor (스키마 수정)

| 항목 | 문제 | 권장 |
|---|---|---|
| `games` | `(platform, external_id)` UNIQUE 없음 | 제약 추가 |
| `raw_games.reviews JSONB` | row 비대화 | 별도 `raw_reviews` 테이블 |
| `game_features` | 시계열 없음 | SCD Type 2 |
| `game_similarities` | 주차별 스냅샷 없음 | `calculated_week` + PK에 포함 |
| 파이프라인 | "Batch Server" 추상적 | Airflow/Prefect/cron 명시 |

### 🟢 잘된 점
- 레이어 분리(Raw/Normalized/Feature/Result) 명확
- Feature Store 중심 설계 방향성 옳음
- Human-in-the-loop 포함
- 4주 일정 현실적

### 💡 Prototype이면 바꿀 3가지
1. 임베딩 + 카테고리 하이브리드: `cosine(desc_embed) * 0.5 + feature_match * 0.5`
2. Top N 검증셋 확보 먼저 (20개 게임 "진짜 경쟁작" 라벨)
3. "경쟁작" 정의 워크샵

---

## Turn 3 — 사용자: 수정 지시 + 추가 질문

### 수정 지시
1. 동일 장르 아니어도 포함
2. "기타" 제거
3. 연속값 기반으로
4. 경쟁작 정의 기준 논의 필요

### 맥락 전환 (중요)
> "아니 게임을 만들고 있는게 아니라 게임 회사의 내부 업무 프로세스를 개선하는 관점으로 보는거야."

경쟁작 분석 자체가 반복 업무 → 자동화 대상. 이 때문에:
- "시장 리서치 자동화(리포트용)"이 우선
- 검수 단계를 두면 "일 2번 하는 것" — HITL 재설계 필요

### 추가 질문
- **Step 1**: Play Store/Steam API 제공? AI로 간접 측정?
- **Step 2**: 가중치는 adaptive할 것 같은데 ground truth 기준은? Target user 겹침?
- **Step 3**: "잘못 잡힌 경쟁작 제거/수동 추가"는 일 2번 아닌가?
- 추가 플랫폼 추천?
- 서버 구조 (batch/analysis/api/fe) 검토
- 부족한 점: 데이터 레이어 설계 — "데이터 파이프라인 + Feature Store + 결과 캐싱" 구체화
- Minor 전부 수정
- 크롤링 ToS는 PoC 단계에서 실제 문제?

### 개별 항목 지시
- #5 (주간 스냅샷): **추가**
- #6 (Feature 품질 측정): **아이디어 내놔**
- #7 (HITL 피드백 루프): **추가**
- #8 (크롤링 ToS): **PoC에서 실제 문제 되는지 확인**
- #9 (Minor 스키마): **전부 수정**

---

## Turn 4 — Assistant: 답변 + 업데이트된 기획

### Q: 경쟁작 정의 (내부 프로세스 관점)

**프레임 전환의 의미**: "경쟁작 분석 도구"가 아니라 **"리서치팀 반복업무 자동화"**. 목적함수가 precision@N에서 **"리포트 준비 시간 X→Y"** 로 바뀜.

**업계 3층 정의**:
| 층 | 정의 | 측정 난이도 |
|---|---|---|
| Direct | 같은 장르·BM·유저층 | 쉬움 |
| Indirect | 유저 시간/지갑 경합 | 어려움 |
| Benchmark | 벤치마킹 대상 | 주관적 |

**실무 6가지 축**: Target user overlap ⭐, Revenue tier, Genre 근접도, BM 유사, 출시 지역/시점, 아트 스타일.
→ PoC에선 1~4만.

### Q Step 1: 플랫폼 API 현실

| 소스 | API | PoC |
|---|---|---|
| Steam Web API | ✅ 공식 | ⭐ |
| SteamSpy | 비공식 | ⭐ 보조 |
| Google Play | ❌ 공식 없음 | gplay-scraper로만 |
| AppMagic / data.ai / SensorTower | ✅ 상용 유료 | 운영 단계 |

**AI 간접 측정**: 설명/스크린샷/트레일러 → multimodal LLM, 리뷰 텍스트 → session/pain point, 아이콘 → 아트 스타일, "Similar apps" signal → weak label.

### Q Step 2: Adaptive 가중치 ground truth

> "target user 층이 겹치는 정도" → **정확히 맞음. 업계 북극성.**

| 신뢰도 | 소스 | PoC |
|---|---|---|
| 최고 | SensorTower cross-install (유료) | X |
| 높음 | **PM 라벨 20~50개** | ⭐ |
| 중간 | 플랫폼 "similar games" signal | ⭐ |
| 낮음 | 리뷰어/유튜브 시청자 겹침 | △ |

PM 라벨 + 플랫폼 similar signal을 weak label로 앙상블.

### Q Step 3: HITL이 "일 2번" 문제

**맞는 지적.** 재설계:
- 경쟁작 "확정" 포기, **"리포트 후보 Top 20" 제시** → PM이 리포트 읽으며 자연스럽게 취사선택
- PM의 upvote/downvote만 유일한 human signal (검수 단계 제거)
- 검수는 "일"이 아닌 **"데이터 생산"** 으로 전환

### 반영 사항

| # | 항목 | 결정 |
|---|---|---|
| 1 | 동일 장르 제약 | 제거 |
| 2 | "기타" | 제거 |
| 3 | 연속값 유사도 | 임베딩 기반 |
| 5 | 주간 스냅샷 | 추가 |
| 6 | Feature 품질 측정 | 아이디어 제시 |
| 7 | HITL 피드백 루프 | 추가 (암묵적 feedback) |
| 8 | 크롤링 ToS | PoC 무시, 운영 전환 시 벤더 검토 |
| 9 | Minor 스키마 | 전부 수정 |

### Q6 Feature 품질 측정 아이디어
1. Gold set (PM 수동 라벨 20개) — field-wise accuracy
2. Self-consistency (같은 게임 3회 일치율 >90%)
3. Cross-model check (Claude vs GPT-4)
4. Canary questions (정답 known yes/no)
5. Downstream proxy (PM upvote rate)
6. Drift detection (주간 재추출 변화율)

---

## Turn 5 — 사용자: 누락된 내용 보충

### 추가 질문
1. Play Store / Steam 외 추가 플랫폼?
2. 서버 구조 검토:
   - batch server (serverless): 경쟁작 데이터 batch search & insert
   - analysis server: python ML batch 분석
   - api-server: FE 데이터 조회만
   - fe: 결과 정리
3. "데이터 파이프라인 + Feature Store + 결과 캐싱" 구체적 설정?

---

## Turn 6 — Assistant: 답변

### 1. 추가 플랫폼

**PoC 즉시 추가**:
- **App Store (iOS)** — 모바일 반쪽 보강. iTunes Search API + app-store-scraper.
- **itch.io** — 인디 조기 트렌드. 공식 API.

**확장**:
- Epic Games Store, TapTap (중화권), Nintendo/PS/Xbox

**메타 시그널 소스 (target user overlap 대리 지표)**:
| 소스 | 시그널 |
|---|---|
| **YouTube Data API** | ⭐ 게임별 시청자 겹침 — target user overlap 최고 대리 지표 |
| Twitch API | Concurrent viewers |
| SteamDB | Concurrent players |
| Google Trends | 검색 트렌드 |

### 2. 서버 구조 평가

초안 합리적. 3가지 보강:
- **Batch를 Collector / Normalizer 2개 stage로 분리** (재시도 단위 다름)
- **Analysis를 Feature Extractor / Similarity Engine 2개로 분리** (LLM 비쌈 vs numpy 저렴)
- **API에 `POST /feedback`만 write** (upvote/downvote 수집)

### 3. 파이프라인 + Feature Store + 캐싱

**파이프라인**:
- PoC 오케스트레이션: **Cron + Python script**로 시작. 커지면 Prefect.
- 멱등성: `(platform, external_id, week_of)` UPSERT
- 실패 격리: stage별 독립 테이블
- 관측성: `pipeline_runs` 테이블

**Feature Store**:
- Feast/Tecton 오버킬. **Postgres + pgvector + 얇은 Python API**로 충분.
- 3기능: SCD Type 2 버저닝 / Point-in-time lookup / 단일 접근 API
- 구현 총량: Python 파일 1개(~150줄), 테이블 2개

**3단계 캐싱**:
1. **LLM 호출 캐시** (`llm_cache` 테이블, sha256 input_hash) — 비용 70%+ 절감
2. **임베딩 캐시** (`embedding_cache`)
3. **유사도 결과 캐시** — `game_similarities_weekly`가 캐시 역할. feature_version 둘 다 안 바뀌면 전주 복사.

**무효화 규칙** (delta-only 재계산):
```
games.updated_at 변경
  → 해당 게임 feature 재추출 (llm_cache hit이면 0)
  → 해당 게임 embedding 재생성
  → 관련 similarity pair만 재계산
  → 나머진 전주 결과 복사
```

---

## Turn 7 — 사용자: "진행해"

Plan mode 내에서 /plan 명령으로 최종 기획서 확인 후 "진행해" 지시.

---

## Turn 8 — Assistant: ExitPlanMode

Plan 승인 받음. 구현 시작 준비.

---

## Turn 9 — 사용자: 프로젝트 디렉토리 + git 초기화 요청

현재 디렉토리 하위에 프로젝트용 디렉토리 만들고 새 git repo 초기화 후 진행 지시.

→ `/home/dyoon/codes/dyoon/game-competitor-analysis-poc/` 생성, `git init` 완료.

---

## 최종 기획서 위치
- **Plan 파일**: `/home/dyoon/.claude/plans/shimmying-chasing-plum.md`
- **프로젝트 리포지토리**: `/home/dyoon/codes/dyoon/game-competitor-analysis-poc/`

## 핵심 결정 정리

| 결정 | 내용 |
|---|---|
| 프레임 | 경쟁작 분석 도구 X → 리서치팀 반복업무 자동화 O |
| 성공 지표 | precision@N 아닌 "PM 리포트 준비 시간 X→Y" |
| 경쟁작 정의 | Target user overlap이 북극성. PoC는 4개 축 연속값 유사도로 근사 |
| 유사도 공식 | `0.40*semantic + 0.25*genre_embed + 0.20*tier + 0.15*bm_kl` |
| Ground truth | PM 라벨 20~50 + 플랫폼 similar signal (weak label) |
| HITL | 검수 단계 제거. upvote/downvote 암묵적 signal만 |
| 아키텍처 | Batch 2-stage + Analysis 2-stage + API(read + /feedback) + FE |
| Feature Store | Postgres + pgvector + 얇은 Python API (Feast X) |
| 캐싱 | LLM + embedding + similarity 3단계, delta-only 재계산 |
| 데이터 소스 | Steam/App Store/Play/itch.io (PoC), YouTube/Twitch (확장) |
| 오케스트레이션 | Cron + Python (PoC) → Prefect (확장) |
