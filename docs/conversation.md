# User Prompt History

---

## Prompt 1

# 🎮 게임 경쟁작 자동 분석 시스템 – 구현 설계서 (Prototype)

---

# 1. 📌 프로젝트 개요

## 1.1 목적

게임 시장 리서치를 자동화하여 **경쟁작 탐색 및 리포트 생성 업무를 효율화**한다.

## 1.2 목표

* 특정 게임 기준 경쟁작 Top N 자동 도출
* 주간 리포트 자동 생성
* 최소한의 Human 검수로 운영 가능

## 1.3 범위 (Prototype 기준)

* 모바일 + PC 일부 (Play Store / Steam 중심)
* Top 게임 약 200개 대상
* 주간 배치 기반

---

# 2. 🧭 시스템 전체 구조

## 2.1 아키텍처

```
[Batch Server]
   ↓
[Raw Data DB]
   ↓
[Normalized DB]
   ↓
[Analysis Server (LLM)]
   ↓
[Feature Store]
   ↓
[Similarity Engine]
   ↓
[Result DB]
   ↓
[API Server]
   ↓
[Frontend]
```

---

# 3. 🗂 데이터 레이어 설계

## 3.1 Raw Data Layer

### 목적

* 원본 데이터 보존
* 재처리 가능성 확보

### 테이블: raw_games

```sql
CREATE TABLE raw_games (
  id SERIAL PRIMARY KEY,
  platform VARCHAR,
  external_id VARCHAR,
  title TEXT,
  description TEXT,
  raw_genre TEXT,
  tags JSONB,
  reviews JSONB,
  update_log TEXT,
  collected_at TIMESTAMP
);
```

---

## 3.2 Normalized Layer

### 목적

* 플랫폼별 데이터 구조 통합
* 중복 제거

### 테이블: games

```sql
CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  platform VARCHAR,
  external_id VARCHAR,
  title TEXT,
  description TEXT,
  genre VARCHAR,
  tags TEXT[],
  updated_at TIMESTAMP
);
```

---

## 3.3 Feature Store (핵심)

### 목적

* 게임을 분석 가능한 구조화 데이터로 변환

### 테이블: game_features

```sql
CREATE TABLE game_features (
  game_id INT PRIMARY KEY,
  genre VARCHAR,
  subgenre VARCHAR,
  bm VARCHAR,
  play_style TEXT[],
  session_length VARCHAR,
  core_loop TEXT,
  feature_version INT,
  created_at TIMESTAMP
);
```

### Feature 정의

| 항목             | 설명                    |
| -------------- | --------------------- |
| genre          | RPG, Puzzle 등         |
| subgenre       | 수집형, 방치형 등            |
| bm             | gacha / ads / premium |
| play_style     | PvP, PvE, idle        |
| session_length | short / medium / long |
| core_loop      | 핵심 반복 구조              |

---

## 3.4 Similarity Result Layer

### 목적

* 계산 결과 캐싱

### 테이블: game_similarities

```sql
CREATE TABLE game_similarities (
  base_game_id INT,
  target_game_id INT,
  similarity_score FLOAT,
  rank INT,
  calculated_at TIMESTAMP,
  PRIMARY KEY (base_game_id, target_game_id)
);
```

---

# 4. 🔄 데이터 파이프라인

## Step 1. 데이터 수집 (Batch Server)

* 크롤링 대상:

  * Play Store
  * Steam

* 수집 항목:

  * 설명
  * 태그
  * 리뷰
  * 업데이트 로그

---

## Step 2. 데이터 정제

```
raw_games → games
```

* 중복 제거
* 필드 정리

---

## Step 3. Feature 추출 (Analysis Server)

### 방식

* LLM 기반 분석

### 입력

* description
* tags
* reviews

### 출력

* Feature JSON

---

## Step 4. 유사도 계산 (Similarity Engine)

### 계산식

```python
score =
  genre_match * 0.4 +
  bm_match * 0.2 +
  play_style_similarity * 0.2 +
  session_length_match * 0.1 +
  기타 * 0.1
```

---

## Step 5. 결과 저장

```
Top N 경쟁작 → game_similarities
```

---

# 5. ⚙️ 서버 구성

## 5.1 Batch Server

* 크롤링
* 신규 게임 탐지

---

## 5.2 Analysis Server

* LLM Feature 추출
* 데이터 정제

---

## 5.3 Similarity Engine

* 유사도 계산
* 경쟁작 선정

---

## 5.4 API Server

* 결과 조회
* 필터링
* 리포트 제공

---

## 5.5 Frontend

* 경쟁작 리스트 표시
* 리포트 시각화

---

# 6. 📊 리포트 구조

## 주간 리포트

### 1. 경쟁작 Top N

* 점수 기반 정렬

### 2. 신규 경쟁작

* 이번 주 추가된 게임

### 3. 경쟁 환경 변화

* 순위 변동
* 신규 진입

### 4. 주요 업데이트 요약

* LLM 기반 요약

---

# 7. 🤖 Human-in-the-loop

## 역할

* Top N 결과 검수
* 일부 수정

## 목표

* 검토 대상 게임 수 최소화 (≤ 20)

---

# 8. ⚡ 성능 및 최적화

## 문제 1: 연산량 증가

* 해결:

  * 동일 장르만 비교
  * Top 후보군 제한

---

## 문제 2: LLM 비용

* 해결:

  * Feature 캐싱
  * 변경된 게임만 재분석

---

# 9. 📅 개발 일정 (4주)

## Week 1

* DB 설계
* 크롤링 구현

## Week 2

* Feature 추출 (LLM)
* 데이터 파이프라인 구축

## Week 3

* 유사도 계산
* 결과 저장

## Week 4

* 리포트 생성
* 테스트 및 튜닝

---

# 10. 🚨 리스크 및 대응

| 리스크         | 대응                |
| ----------- | ----------------- |
| Feature 정확도 | 카테고리 단순화          |
| 데이터 부족      | 플랫폼 확장            |
| 조직 신뢰 부족    | explainable 결과 제공 |

---

# 11. 🔥 핵심 원칙

1. 완벽보다 일관성
2. 자동화 + 사람 검수
3. 결과 캐싱 필수
4. Feature Store 중심 설계

---

# 12. 📌 결론

본 시스템은 단순한 경쟁작 탐색 도구가 아니라
**게임 데이터를 구조화하고 지속적으로 분석하는 데이터 파이프라인**이다.

최종 목표는:

* 반복 업무 제거
* 시장 변화 자동 감지
* 의사결정 지원

---

# 🚀 향후 확장

* 광고 데이터 연동
* 유저 행동 기반 유사도 개선
* 추천 시스템 확장
* 실시간 트렌드 분석

---


이거 분석해봐

---

## Prompt 2

1. 동일장르 아니어도 포함
2. 기타는 제거
3. 연속성 기반으로 쓰자 그럼
4. 게임 서비스에서 경쟁작을 정의하는 기준을 어떻게 정해야될까?
아니 게임을 만들고 있는게 아니라 게임 회사의 내부 업무 프로세스를 개선하는 관점으로 보는거야.
게임 회사에서는 지속적으로 경쟁작을 선정하고 분석해야 되는데 결국 이것도 반복 업무잖아? 주기적으로 찾아야 하니까
근데 이 부분을 자동화하려면 어쨌든 경쟁작 이라는걸 정의부터 해야할 것 같아서
1. Step 1: 게임을 Feature로 분해
- 이 정보들을 google store 나  steam 같은 게임 플랫폼에서 가져올 수가 있어?
- 자동화하려면 api 를 제공해줘야 되잖아
- 안된다면 ai 활용해서 간접 측정할 방법이라도 있나

2.  Step 2: 유사도 계산 모델 만들기
- 이 계산 모델이라는 것도 내가 보기엔 가중치가 하나의 최적해로 고정되는게 아니라 그때 그때 adaptive 하게 바뀔 것 같은데 그럼 최종적으로 그 계산이 맞다 라는 점수를 측정하기 위한 최종 기준이 필요하잖아
- 그건 어느 값으로 하면 되지 결국 target user 층이 겹치는 정도로 보면 되나

3. PM/분석가가:
잘못 잡힌 경쟁작 제거
중요한 경쟁작 수동 추가
- 이걸 할거면 그냥 일 2번 하는거잖아
시장 리서치 자동화 (리포트용)
- 아무래도 이거지 우선은?
이거 실제 프로토타입으로 만들게 개발 기획 짜봐
- 앞에 내용 인데 이거 추가하면 맥락이 좀 생기나?
5. 추가해
6. 이건 아이디어 내놔봐
7. 이것도 추가해
8. 이거 실제로 문제가 돼? 우선은 poc 단계인데 
9. minor는 다 수정해

---

## Prompt 3

내용이 빠졌네 
https://chatgpt.com/share/69df5904-82a0-83e8-9204-3bcab634de07

이거 읽어져?

---

## Prompt 4

게임 서비스에서 경쟁작을 정의하는 기준을 어떻게 정해야될까?
아니 게임을 만들고 있는게 아니라 게임 회사의 내부 업무 프로세스를 개선하는 관점으로 보는거야.
게임 회사에서는 지속적으로 경쟁작을 선정하고 분석해야 되는데 결국 이것도 반복 업무잖아? 주기적으로 찾아야 하니까
근데 이 부분을 자동화하려면 어쨌든 경쟁작 이라는걸 정의부터 해야할 것 같아서
1. Step 1: 게임을 Feature로 분해
- 이 정보들을 google store 나  steam 같은 게임 플랫폼에서 가져올 수가 있어?
- 자동화하려면 api 를 제공해줘야 되잖아
- 안된다면 ai 활용해서 간접 측정할 방법이라도 있나

2.  Step 2: 유사도 계산 모델 만들기
- 이 계산 모델이라는 것도 내가 보기엔 가중치가 하나의 최적해로 고정되는게 아니라 그때 그때 adaptive 하게 바뀔 것 같은데 그럼 최종적으로 그 계산이 맞다 라는 점수를 측정하기 위한 최종 기준이 필요하잖아
- 그건 어느 값으로 하면 되지 결국 target user 층이 겹치는 정도로 보면 되나

3. PM/분석가가:
잘못 잡힌 경쟁작 제거
중요한 경쟁작 수동 추가
- 이걸 할거면 그냥 일 2번 하는거잖아
시장 리서치 자동화 (리포트용)
- 아무래도 이거지 우선은?
이거 실제 프로토타입으로 만들게 개발 기획 짜봐
1. play store / steam 이외에 추가할만한 플랫폼
2. 내부 툴로 사용 목적이니까 각 서버의 역할은 내가 그리는 그림으론
- batch server (serverless batch function) : 경잭작 데이터 batch search 및 insert
- analysis server : python ml 로 새로운 데이터에 대한 분석 batch 실행
- api-server : fe 에서 data 조회에만 사용
- fe : 결과 정리 페이지

이렇게 되면 되지 않을까?
👉 부족한 점: 데이터 레이어 설계

✔ 내가 추천하는 최종 형태

"데이터 파이프라인 + Feature Store + 결과 캐싱" 구조
이건 구체적으로 어떻게 설정할건데
이게 전체 복사가 안되는데

---

## Prompt 5

진행해

---

## Prompt 6

아 잠깐만 지금 directory 하위에 이 프로젝트 용 directory 하나 만들고 거기에 새 git repo 하나 설정하고 거기서 진행해

---

## Prompt 7

1. 뭐 왜 하나씩 계속 실행하는거야 plan mode 에서 왜 진행하고 있어
2. 그리고 이거 답변은 필요없고 내 대화내역 docs 디렉토리 하나 만들어서 거기 md 파일로 하나 만들어놔

---

## Prompt 8

아니 저장하고 끝이 아니라 plan 진행하라고

---

## Prompt 9

https://github.com/hyukyyy/game-competitor-analysis-poc
여기 일단 import 하자

---

## Prompt 10

1. hyukyyy 이 계정 
2. 그리고 다른 데서 구현 이어서 할거니까 plan 구현된 부분 update 해서 docs 로 포함해놔

---

## Prompt 11

remote 설정 한거야?

---

## Prompt 12

설정해 내가 아까 준 repo ㄹ

---

## Prompt 13

1. repo 있고 그래서 내가 push 했음
2. 토큰 이슈 그만 얘기해 
3. @docs/conversation.md 이거 이렇게 해석이나 추가 설명 붙이지 말고 내가 입력한 프롬프트 내역만 저장해
