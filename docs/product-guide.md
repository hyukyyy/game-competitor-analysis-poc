# 기획 및 사용 가이드 (PM용)

> 작성일: 2026-04-18 · 기준: commit `5e6370f` · 대상 독자: PM · 기획자 · 리서처

## 1. 무엇을 해결하나 (Why)

**문제**

- 게임 리서치팀 PM 은 매주 월요일 아침 경쟁작을 수동으로 조사해 리포트를 작성한다.
- 스토어 검색 → 장르/BM/리뷰 뒤져보기 → 스프레드시트 정리 → 문서화 = 몇 시간 소요.
- 담당 게임이 여러 개면 월요일이 통째로 녹는다.

**목표**

- 이 PoC 의 성공 지표는 **리포트 준비 시간 X → Y** 이다. `precision@N` 이 아니다.
- 시스템이 경쟁작을 "확정" 할 필요는 없다. **후보를 제시**하고 PM 이 리포트 작성 시 취사선택하면 충분하다.

**범위**

- Steam 기준 (PC). App Store / Play Store 는 수집만 되고 `add-my-game` 은 아직 Steam 전용.
- Top 게임 약 200개 풀에서 유사도 계산.
- 주간 배치. 실시간 아님.

---

## 2. "경쟁작" 의 정의

**본질적 정의**: "target user 층이 겹치는 정도."
직접 측정이 어려우므로 PoC 는 **4개 축의 연속값 유사도**로 근사한다.

| 축 | 표현 방식 | 가중치 (초기) |
|---|---|---|
| Semantic similarity | description + review 임베딩 cosine | **0.40** |
| Genre/subgenre | LLM 추출 후 장르 텍스트 임베딩 cosine (카테고리 이진 매칭 X) | **0.25** |
| Tier similarity | `log1p(review_count)` 정규화 후 거리 기반 Gaussian | **0.20** |
| BM (business model) | `{gacha, ads, premium, sub}` 확률분포 KL 대칭거리 | **0.15** |

- **동일 장르 제약 없음**, **"기타" 카테고리 없음**, **연속값 기반**.
- 가중치는 PM 피드백 + platform similar signal 로 **자동 재튜닝**된다 (아래 §6 참조).
- 각 게임별 component score (4개) 는 리포트·FE 에 **함께 노출** — 왜 경쟁작인지 설명 가능.

---

## 3. Ground truth (품질 측정 기준)

1. **PM 수동 라벨** — 담당 게임별 "진짜 경쟁작 Top 5" 를 20~50개 엔트리 기록. 현재 `pm_feedback` 이 이 역할 대리.
2. **Platform similar signal (weak label)** — Steam "More Like This", tag overlap 기반 자동 수집. `weak_similarities` 테이블.
3. 위 두 신호로 `tune-weights` 가 grid search → 최적 가중치 → `weight_history` 저장.

명시적 "검수·승인" 플로우 없음 — PM 은 리포트만 소비 + 👍/👎 클릭 만.

---

## 4. PM 사용 플로우 (5단계)

### ① 내 게임 등록

개발자에게 Steam AppID 를 전달하거나, 본인이 CLI 로 직접:

```bash
gca add-my-game --platform steam --appid 1063730
# → ✓ registered my_game id=1 title='New World: Aeternum' (steam:1063730)
```

이 게임이 `is_my_game = TRUE` 로 표시되며, 이후 배치가 **이 게임을 base 로만** 경쟁작을 계산한다.
여러 게임을 등록하면 각각 독립적으로 경쟁작·리포트가 생성된다.

> ℹ️ 현재 Steam AppID 만 지원. App Store / Play Store 는 다음 이터레이션.

<!-- TODO: 스크린샷 — "add-my-game" CLI 출력 -->

### ② 주간 배치 실행

개발자(또는 cron) 이 주 1회:

```bash
# 자세한 배치 블록은 docs/cli-guide.md §4 참조
gca collect:steam --fetch-reviews
gca normalize
gca extract-features --changed-only
gca embed --changed-only
gca weak-labels --source tag_overlap
gca tune-weights
gca similarity
gca report
```

이 끝나면 DB 에 리포트가 쌓인다. PM 은 FE 만 열면 된다.

### ③ FE 에서 내 게임 확인 — `/`

- URL: `http://<deploy-url>/` (프로덕션) 또는 `http://localhost:3000` (로컬)
- 내 게임 카드 그리드 — 각 카드에 `Competitors` / `Report` 버튼.
- 구현: [web/app/page.tsx](../web/app/page.tsx) — `api.listGames({ mine: true })`.

<!-- TODO: 스크린샷 — "/" My Games 그리드 -->

### ④ 경쟁작 분석 — `/games/<id>`

- Top 10 경쟁작 테이블.
- 컬럼: Rank · Title · Platform · Overall score · **semantic / genre / tier / bm component bar**.
- 각 row 에 👍 / 👎 버튼 → 클릭 시 `POST /feedback` 으로 signal 기록.
- 구현: [web/app/games/\[id\]/page.tsx](../web/app/games/%5Bid%5D/page.tsx) + [CompetitorsTable.tsx](../web/app/games/%5Bid%5D/CompetitorsTable.tsx) (client component).

<!-- TODO: 스크린샷 — "/games/1" 경쟁작 테이블 + component bar -->

### ⑤ 주간 리포트 — `/games/<id>/report`

- 가장 최근 주차 리포트 (Markdown 렌더링).
- 섹션: Top N 경쟁작 · 신규 진입 · 순위 변동 · 업데이트 요약.
- 구현: [web/app/games/\[id\]/report/page.tsx](../web/app/games/%5Bid%5D/report/page.tsx) (react-markdown + 커스텀 component 매핑).

<!-- TODO: 스크린샷 — "/games/1/report" 리포트 뷰 -->

---

## 5. 리포트 구조 해설

템플릿: [src/gca/report/templates/weekly.md.j2](../src/gca/report/templates/weekly.md.j2)

| 섹션 | 어떤 의사결정에 쓰나 |
|---|---|
| **Top N Competitors** (+ component 점수) | 이번 주 경쟁구도 한눈에. component bar 가 낮은 축이 있으면 "이 경쟁작은 장르만 같고 BM 은 다르네" 같은 정성 판단 가능 |
| **New Entrants This Week** | 이전 주에 없던 게임이 Top N 에 들어왔을 때. 시장 신규 진입 / 급성장 신호 |
| **Rank Changes vs Last Week** | 순위 상승/하락 폭. 지속 상승하는 경쟁작은 집중 분석 대상 |
| **Notable Updates Summary** (LLM 요약) | 업데이트/패치 요약 — 리서치 시간 가장 많이 잡아먹는 부분 |
| **footer: weights + component 의미** | 이번 주 사용된 가중치 공개 (explainability) |

---

## 6. 피드백의 의미

FE 에서 👍/👎 를 누르면 일어나는 일:

```
👍 클릭
  → POST /feedback { signal: "upvote", base_game_id, target_game_id, week_of }
  → pm_feedback 테이블에 row 추가
  → 다음 주 gca tune-weights 가 이 signal 들을 grid search 입력으로 사용
  → 가중치 (semantic / genre / tier / bm 의 비율) 가 조금씩 조정됨
  → 다음 주 리포트의 Top N 순서가 PM 선호에 더 가깝게 변함
```

- **검수·승인 플로우 없음** — 👍/👎 만 남기면 된다.
- **피드백이 적을수록 기본 가중치 (0.40/0.25/0.20/0.15) 유지**. 10~20개 모이면 의미 있는 튜닝 시작.
- 👎 는 " 이건 내가 생각하는 경쟁작이 아님" 신호. 👍 와 비대칭으로 더 강하게 반영.

---

## 7. 범위 및 한계

| 항목 | 현재 상태 |
|---|---|
| 플랫폼 | Steam 만 `add-my-game` 지원. App Store / Play Store 는 수집만 |
| 인증 | 없음 — 프로토 단계. 프로덕션 전 **Vercel password protection** 으로 우선 차단 권장 |
| 배치 자동화 | 없음 — 개발자 수동 실행 또는 GitHub Actions cron (후속 작업) |
| 실시간 | 불가 — 주간 스냅샷만 |
| `POST /reports/generate` | Vercel 배포 환경에서는 불가 (sentence-transformers 50MB 초과). 로컬/cron 에서만 |
| 인디 long-tail | Top 200 위주. long-tail 은 범위 밖 |

### 후속 작업 (범위 밖)

- 인증·권한 (Internal SSO 또는 Supabase Auth)
- GitHub Actions cron 으로 배치 자동화
- App Store / Play Store `add-my-game` 지원
- ML-free weight loading 으로 `POST /reports/generate` 를 serverless 에서 동작
- PM 실데이터 수집 → 가중치 재튜닝 A/B 측정

---

## 관련 문서

- [docs/service-architecture.md](./service-architecture.md) — 시스템 전체 구조, 데이터 흐름, DB 스키마
- [docs/cli-guide.md](./cli-guide.md) — 개발자·운영자용 CLI 레퍼런스 (배치 실행 블록 포함)
- [docs/not-done.md](./not-done.md) — 남은 작업 목록
- [docs/plan.md](./plan.md) — 초기 기획 원문 (히스토리)
