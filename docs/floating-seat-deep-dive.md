# Floating Seat 대기열 — 기술 심화 설명 (면접 딥다이브 대비)

> `interview-technical-challenges.md` 사례 5의 상세 버전.
> 근거 코드: `src/seat/seat.repository.ts`, `src/seat/seat.service.ts`, `src/seat/seat.constants.ts`

---

## 0. Redis 용어 정리 (사전 지식)

### 자료구조

| 자료구조 | 설명 | 이 시스템에서의 용도 |
|---|---|---|
| **STRING** | 가장 기본. 키 하나에 값 하나 | device ID 저장, grace/쿨다운 마커 (값보다 "키의 존재 여부"가 의미) |
| **SET** | 중복 없는 값들의 집합. 순서 없음 | 점유자 목록, 소켓 목록, 무효화된 기기 목록 — "중복 불가"가 핵심 |
| **LIST** | 순서 있는 값 목록. 양쪽 끝에서 넣고 뺄 수 있음 | FIFO 대기열 (뒤로 넣고 앞에서 꺼냄) |
| **HASH** | 키 하나 안에 field-value 쌍 여러 개 (객체처럼) | 양보 요청 메타데이터 (보낸 사람, 만료 시각 등) |

### 명령어

| 명령어 | 풀네임 | 동작 | 예시 |
|---|---|---|---|
| **SADD** | **S**et **ADD** | SET에 원소 추가. 이미 있으면 무시(멱등) | `SADD occupants user1` → 점유자 등록 |
| **SREM** | **S**et **REM**ove | SET에서 원소 제거 | `SREM occupants user1` → 점유 해제 |
| **SCARD** | **S**et **CARD**inality | SET의 원소 개수 반환 (cardinality = 집합의 크기) | `SCARD occupants` → 현재 점유 좌석 수 |
| **SISMEMBER** | **S**et **IS MEMBER** | 원소가 SET에 있는지 확인 (1/0 반환) | `SISMEMBER occupants user1` → 이미 점유 중인가? |
| **RPUSH** | **R**ight **PUSH** | LIST 오른쪽 끝(뒤)에 추가 | 대기열 맨 뒤에 줄서기 |
| **LREM** | **L**ist **REM**ove | LIST에서 특정 값 제거. **제거한 개수를 반환** | 대기열에서 특정 유저 빼기 (반환값 0이면 "줄 서있지 않았음") |
| **DEL** | **DEL**ete | 키 자체를 삭제 | ACK 도착 시 ack_pending 키 제거 |
| **EXPIRE / TTL** | — | 키에 수명(초) 설정 / 남은 수명 조회. 만료되면 자동 삭제 | grace 키 10초, revoked_devices 14일 |
| **MULTI / EXEC** | — | 여러 명령을 묶어 원자적으로 실행 (트랜잭션). 단, **앞 명령의 결과를 읽어 분기할 수 없음** | (이 시스템에선 한계 때문에 안 씀 → Lua 사용) |
| **WATCH** | — | 낙관적 락: 감시 중인 키가 다른 클라이언트에 의해 바뀌면 트랜잭션 취소 | (경합 시 재시도 루프가 필요해서 안 씀) |

### 기타 용어

- **Lua 스크립트**: Redis 서버 안에서 실행되는 작은 프로그램. 여러 명령을 "읽고 → 조건 분기하고 → 쓰는" 것까지 **하나의 원자 단위**로 실행할 수 있다. Redis는 단일 스레드라 스크립트 실행 중 다른 명령이 끼어들 수 없음
- **멱등(idempotent)**: 같은 연산을 여러 번 해도 결과가 한 번 한 것과 같음. `SADD`가 대표적 — 이미 있는 원소를 또 넣어도 변화 없음
- **TTL (Time To Live)**: 키의 수명. 만료되면 Redis가 자동으로 키를 삭제
- **FIFO (First In First Out)**: 먼저 들어온 것이 먼저 나가는 큐. 줄서기와 동일
- **check-then-act**: "확인하고 나서 행동"하는 패턴. 확인과 행동 사이에 다른 프로세스가 끼어들면 깨진다 (race condition의 전형)
- **CAS (Compare-And-Swap)**: "값이 내가 아는 그대로면 바꾸고, 아니면 실패"를 원자적으로 수행하는 동시성 기법. CPU 명령어 수준의 개념인데, Lua 스크립트가 Redis에서 같은 역할을 한다

---

## 1. 왜 Redis가 "단일 진실 원천"인가

좌석 상태는 **초 단위로 바뀌는 휘발성 데이터**다 (로그인, 탭 닫기, 네트워크 순단). DB에 두면:

- 로그인마다 row 락 경합 발생 → hot path에 부적합
- 소켓 끊김 같은 고빈도 이벤트마다 DB write
- 서버 인스턴스가 여러 대라 인메모리로는 불가능 → 공유 저장소 필수

그래서 **"현재 누가 앉아있나"는 전부 Redis**, 영속이 필요한 것(`max_seat_count`, `is_seat_managed`, allowlist)만 DB에 둔다.

### 핵심 키 구조 (총 ~14종 중 핵심 3종)

| 키 | 자료구조 | 의미 |
|---|---|---|
| `seat:company:{id}:occupants` | **SET** | 점유자 userId 집합. **`SCARD`(원소 수) = 사용 중 좌석 수** |
| `seat:company:{id}:waiting` | **LIST** | FIFO 대기열 |
| `seat:user:{id}:sockets` | **SET** | 살아있는 WebSocket ID 집합. **비어있지 않으면 "In Use"** |

설계 포인트:
- 별도 카운터 없이 **집합 크기 자체가 카운트** → 카운터-집합 불일치가 원천적으로 불가능
- SET이므로 같은 유저가 두 번 로그인해도 SADD는 멱등 → 좌석 2개 점유 불가

---

## 2. Lua 스크립트 — check-then-act race의 원자화 (핵심)

### 문제: 확인과 행동 사이의 틈

```
서버A: SCARD occupants → 9   (정원 10, 1자리 남음)
서버B: SCARD occupants → 9   ← A가 SADD 하기 전에 읽음
서버A: SADD user1 → 점유 10
서버B: SADD user2 → 점유 11  ❌ 정원 초과
```

"확인"과 "행동"이 분리된 한, 다중 인스턴스에서는 반드시 깨진다. DB라면 트랜잭션+락으로 풀겠지만 Redis에서는 **Lua 스크립트가 그 역할**을 한다 — Redis는 단일 스레드라서 **스크립트 실행 중 다른 명령이 절대 끼어들 수 없다**. CPU의 compare-and-swap을 Redis 레벨로 올린 것과 같다.

### TRY_ACQUIRE — 좌석 획득

```lua
if redis.call('SISMEMBER', KEYS[1], userKey) == 1 then
  return {1, 'granted'}                            -- ① 이미 점유 중 → 멱등 성공
end
if redis.call('SCARD', KEYS[1]) >= maxSeats then
  return {0, 'company_max'}                        -- ② 만석 → 거절
end
redis.call('SADD', KEYS[1], userKey)               -- ③ 빈자리 → 점유
return {1, 'granted'}
```

- ①은 **멱등성**: 새로고침/재로그인이 "이미 네 자리야"로 끝남 — 중복 차감 없음
- ②③이 한 덩어리 → 마지막 1자리에 100명이 동시에 와도 정확히 1명만 성공

### TAKEOVER_INACTIVE — 비활성 점유자 좌석 뺏기

시나리오: 만석인데 점유자 중 한 명이 "Not Using"(접속 끊긴 채 좌석만 보유) → 대기자가 직접 뺏기.

```lua
if redis.call('SISMEMBER', occupantsKey, targetUser) == 0 then
  return {0, 'not_occupant'}      -- 대상이 이미 다른 경로로 해제됨
end
if redis.call('SCARD', targetSocketKey) > 0 then
  return {0, 'target_active'}     -- ★ 대상이 그 사이 재접속 → 뺏으면 안 됨
end
redis.call('SREM', occupantsKey, targetUser)   -- 대상 제거
redis.call('SADD', occupantsKey, takerUser)    -- 내가 입장 (제거+추가 = 한 단위, 좌석 수 불변)
```

어려운 race: **화면에 Not Using으로 보여 뺏기를 눌렀는데 그 0.5초 사이 대상이 재접속**. 조건 검사와 swap이 원자적이므로 재접속이 한 순간이라도 빨랐다면 `target_active`로 실패하고 아무것도 변하지 않는다. SREM+SADD가 같은 스크립트라 "제거만 되고 추가 안 된" 중간 상태를 다른 서버가 관측할 수 없다.

### ASSIGN_WAITING — 매니저의 대기열 강제 할당

```lua
if SISMEMBER(occupants, userId) → LREM + 'already_occupant'  -- 멱등 + 대기열 정리
if SCARD(occupants) >= maxSeats → 'company_max'
removed = LREM(waiting, 0, userId)
if removed == 0 → 'not_waiting'    -- ★ 대기열에 없으면 좌석도 안 줌
SADD(occupants, userId)
```

포인트: **LREM 반환값을 조건으로 사용** — "대기열에서 빠짐"과 "좌석 획득"이 반드시 함께 일어난다. 분리하면 "대기열에서는 빠졌는데 그 사이 만석이 돼 좌석은 못 받은" 미아 상태가 생긴다.

---

## 3. 상태 머신 — "점유 ≠ 접속"의 분리

가장 중요한 설계 결정. 순진하게 "소켓 끊김 = 자리 반납"으로 만들면:

- 새로고침(F5) → 소켓 재연결 사이에 자리를 잃고, 만석이면 대기열 꼴찌
- 탭 2개 중 1개만 닫음 → 자리 잃음
- 와이파이 1초 순단 → 자리 잃음

그래서 상태를 분리했다:

```
                 좌석 보유 (occupants SET)
                 ┌──────────────┬──────────────┐
                 │   보유 O     │   보유 X     │
소켓 있음(active)│  In Use      │  (비정상)    │
소켓 없음        │  grace(10s)  │  waiting     │
                 │  → Not Using │  or 미접속   │
```

- 마지막 소켓이 끊겨도 좌석은 유지된 채 `grace` 키(10s TTL)만 생성 → 10초 내 재접속 시 아무 일도 없었던 듯 복귀 (새로고침이 이 경로)
- grace 만료 → **"비활성 점유(Not Using)"**: 좌석은 보유하되 takeover 대상이 됨
- **좌석 회수는 오직 명시적 이벤트로만**: 로그아웃 / 매니저 강제 해제 / 양보 요청 수락·타임아웃 / takeover

즉 "끊김"이라는 모호한 신호로는 절대 좌석을 뺏지 않고, 뺏을 권한을 **명시적 행위자**(본인·매니저·대기자)에게만 부여했다.

---

## 4. Bull 지연 잡 — 타임아웃을 "예약된 작업"으로

"10초 뒤 grace 만료 처리" 같은 미래 시점 작업의 선택지별 문제:

- `setTimeout`: 서버 재시작/배포 시 타이머 증발
- Redis key TTL + keyspace notification: 만료 알림이 at-most-once라 유실 가능, 수신 인스턴스도 불특정

→ **Bull(Redis 기반 잡 큐)의 delayed job**: 잡이 Redis에 영속되므로 서버가 재시작돼도 예약이 살아있다.

| 잡 | 지연 | 하는 일 |
|---|---|---|
| `grace-expire` | 10s | 재접속 없으면 active/device 정리 → "Not Using" 확정 |
| `pending-bind-expire` | 30s | 좌석을 줬는데 WS 바인딩이 안 오면(로그인 직후 브라우저 닫음) 회수. 잡에 `sessionId`를 넣어 **그 grant 세션의 잡인지 대조** — 유저가 그새 정상 재로그인했는데 옛 잡이 자리를 뺏는 stale 실행 방지 |
| `idle-kick` | 120s | 양보 요청을 수락도 거절도 안 하면 강제 퇴출 |
| `request-ack-timeout` | 5s | 요청에 클라이언트 ACK조차 없으면(브라우저 닫힘 = 응답 불가) 120초를 기다리지 않고 **fast-kick** |

`request-ack-timeout`의 묘미: "대상이 살아있는데 고민 중"(120s 대기)과 "대상이 아예 없음"(5s 컷)을 **ACK 수신 여부로 구분** — 빈 의자에 120초를 낭비하지 않는다.

---

## 5. 유령 대기자(ghost waiting) 정리

문제: 대기열 진입 후 브라우저를 닫으면? LIST 원소에는 **개별 TTL을 걸 수 없으므로** 그 자리는 영원히 남고 뒷사람들은 영원히 대기한다.

해결: 대기자마다 별도 키 `seat:user:{id}:waiting_seen`(10s TTL)을 두고 **클라이언트의 상태 폴링이 올 때마다 TTL 갱신** — "마커가 살아있다 = 브라우저가 살아있다"는 heartbeat. `pruneDeadWaiting`이 좌석 할당/상태 조회 시점에 대기열을 돌며 마커가 만료된 유저를 LREM으로 제거한다.

디테일: 대기열에 막 들어와 아직 첫 폴링이 도착하기 전인 신규 대기자가 prune에 휩쓸리지 않도록, **대기열 진입 시점에 마커를 선제 생성**한다.

---

## 6. 디바이스 강제 교체 — revoked_devices와 TTL 정렬

정책: 1 user = 1 device. 새 기기 로그인 시 기존 기기를 밀어낸다.

문제: **밀려난 기기가 이미 유효한 JWT를 들고 있다** — JWT는 stateless라 서버가 "그 토큰 무효"라 할 방법이 기본적으로 없다.

해결:
1. takeover 시 밀려난 deviceId를 `seat:user:{id}:revoked_devices` SET에 기록
2. `RequestAuthGuard`가 **매 요청마다** 토큰 payload의 deviceId를 이 SET과 대조 → 일치하면 401

핵심 디테일 — **TTL = 1,209,600초(14일) = refresh token 수명과 정확히 동일**:
- 블랙리스트 TTL이 토큰 수명보다 짧으면, 블랙리스트가 먼저 만료된 뒤 구 기기가 아직 살아있는 refresh token으로 **되살아난다**
- "차단 기록은 차단 대상 토큰보다 오래 살아야 한다"는 토큰 무효화 원칙을 TTL로 구현
- 14일 후엔 토큰이 자연 만료되므로 블랙리스트도 자동 청소 (영구 보관 불필요)

---

## 7. 점진 도입 — is_seat_managed

전 유저에게 한 번에 켜면 배포 직후 기존 활성 유저 전원이 좌석 시스템에 편입되어 대규모 차단 위험.

→ `company_user_rel.is_seat_managed` 컬럼(default **0** = bypass):
- 기존 유저: 전부 0으로 백필 → 좌석 로직 자체를 건너뜀 (기존 동작 유지)
- **신규 "Add Account" 경로로 추가되는 유저만 1** → 좌석 관리 대상

신규 진입점에서만 새 시스템을 적용해 점진 전환 — **출시일에 행동이 바뀌는 유저 0명**. feature flag를 per-user 데이터로 구현한 셈.

---

## 면접용 한 줄 요약

> "분산 환경의 check-then-act race를 Redis Lua로 원자화하고, '접속'과 '점유'를 분리한 상태 머신으로 순단/멀티탭 문제를 풀었으며, 타임아웃은 서버 재시작에도 살아남는 지연 잡으로, 토큰 무효화는 refresh 수명과 정렬된 TTL 블랙리스트로 처리했다."

## 면접관이 깊게 팔 가능성이 높은 지점

1. **"왜 MULTI/EXEC나 WATCH가 아니라 Lua인가?"**
   - MULTI/EXEC는 명령들을 원자적으로 *실행*만 할 뿐, 앞 명령의 *결과를 읽어 분기*할 수 없다 (SCARD 결과에 따라 SADD 여부 결정 불가)
   - WATCH는 낙관적 락이라 경합 시 재시도 루프 필요 — 로그인 폭주 시점에 최악
   - Lua는 읽기→분기→쓰기를 서버 사이드에서 단일 원자 단위로 수행
2. **"TTL이 왜 하필 14일인가?"** → 위 6번 (refresh token 수명 정렬)
3. **"Redis가 죽으면?"** → 좌석 상태는 재구성 가능한 휘발성 상태(로그인 시 재획득). 영속 필요 데이터는 DB에 분리 보관
4. **"획득/해제 단위 불일치 함정"** → 획득은 user 단위 멱등(+1 한 번)인데 해제를 socket 단위(-1 per socket)로 다루면 멀티탭에서 모델 불일치 — 획득/해제의 단위를 반드시 일치시켜야 한다
