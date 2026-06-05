# 기술 면접 대비 — 기술적으로 어려웠던 문제 해결 사례

> 출처: zenapp API 서버 리팩토링/최적화 작업 (2026)
> 용도: "기술적으로 어려웠던 문제와 해결 경험" 질문 대비

---

## 🥇 사례 1: 대용량 JSON 저장 성능 최적화 (성능/백엔드 딥다이브용)

### 상황 (Situation)
- 건축 설계 솔루션 저장 API가 4~8MB JSON payload(`layout_lookup`, `geometry`, `input_set`, `core_relation`)를 처리
- 동시 저장 요청이 몰리면 응답 지연 + DB 커넥션 풀 경합 발생

### 문제 (Problem) — 왜 어려웠나
1. 요청 body를 `JSON.parse` → 다시 `JSON.stringify`하는 왕복 직렬화에 payload당 200~800ms 소요
2. 변경되지 않은 필드까지 매번 통째로 UPDATE → 불필요한 write + redo log 부담
3. 기존 방식은 SELECT(해시 비교) → UPDATE 2회 왕복이라 동시성 환경에서 커넥션 점유 시간이 길어짐

### 해결 (Action)
1. **Zero-copy raw field extraction** (`src/project/solution/raw-json-fields.ts`, ~175줄)
   - raw JSON 문자열을 파싱 없이 단 한 번의 O(n) 스캔으로 처리
   - escape 문자와 중첩 object/array depth를 char-code 레벨에서 직접 추적하며 대형 필드의 substring을 그대로 추출
   - parse/stringify 왕복 제거
2. **서버사이드 해시 비교 delta update** (`solution.repository.ts`)
   - MD5 해시를 컬럼에 함께 저장, MySQL `IF()` 조건으로 단일 쿼리 내에서 변경된 필드만 갱신
   ```sql
   SET layout_lookup = IF(layout_lookup_hash = :new_hash, layout_lookup, :new_value),
       layout_lookup_hash = IF(layout_lookup_hash = :new_hash, layout_lookup_hash, :new_hash)
   ```
   - DB 왕복 2회 → 1회, 동일 값 할당은 MySQL이 물리적 write 스킵
3. **벤치마크로 검증** (`solution-save.benchmark.spec.ts`, 316줄)
   - 4MB 추출 <100ms / 8MB <200ms
   - 동시 20건 4MB 저장 P95 <1초
   - version-only 업데이트 <10ms
   - 성능 기준을 테스트로 고정해 회귀 자동 감지

### 결과 (Result)
- 직렬화 오버헤드 제거 + DB 왕복 절반으로 대용량 저장 latency 대폭 개선
- 성능 회귀를 벤치마크 테스트로 방지하는 체계 구축

### 면접 포인트
- "프로파일링으로 병목 특정 → 알고리즘적 해결(O(n) 스캔) → DB 레벨 최적화(IF 조건 delta) → 벤치마크 검증"의 완결된 서사
- 라이브러리 교체가 아니라 escape/depth 추적 파서를 직접 구현한 점이 차별화 요소

### 예시 답변 스크립트 (~90초)
> "최근에 건축 설계 SaaS의 API 서버에서 4~8MB짜리 JSON 솔루션 데이터를 저장하는 API의 성능 문제를 해결한 경험이 있습니다. 프로파일링해보니 병목은 DB가 아니라, 요청 body를 parse했다가 다시 stringify하는 직렬화 왕복에서 200~800ms가 소요되는 것이었습니다.
>
> 두 가지로 접근했습니다. 첫째, raw JSON 문자열을 파싱하지 않고 한 번의 O(n) 스캔으로 — escape 문자와 중첩 depth를 직접 추적하면서 — 대형 필드의 substring만 추출하는 zero-copy 추출기를 직접 구현해 직렬화 왕복을 제거했습니다. 둘째, 기존에 SELECT로 해시를 읽고 UPDATE하던 2회 왕복을, MySQL의 IF() 조건을 활용해 변경된 필드만 갱신하는 단일 쿼리 delta update로 합쳤습니다.
>
> 마지막으로 동시 20건의 4MB 저장에서 P95 1초 미만, 버전만 바뀐 저장은 10ms 미만이라는 기준을 벤치마크 테스트로 고정해서, 이후 회귀를 자동으로 잡을 수 있게 했습니다."

### 예상 꼬리 질문
- Q. 왜 스트리밍 파서(예: JSONStream) 대신 직접 구현했나? → 전체 파싱이 목적이 아니라 특정 top-level 필드의 raw substring 추출만 필요. 범용 파서는 토큰화 오버헤드가 있고, 추출 후 다시 stringify가 필요해짐
- Q. 해시 충돌 우려는? → MD5는 보안 목적이 아닌 변경 감지 목적. 우발적 충돌 확률(2^-64 수준)은 비즈니스 리스크 대비 무시 가능
- Q. MySQL IF()가 물리 write를 스킵하는 근거는? → MySQL은 동일 값 할당 시 row를 dirty로 표시하지 않아 redo log/disk write 생략

---

## 🥈 사례 2: NestJS 순환 의존성 해결 + God Class 분해 (시스템 설계/시니어용)

### 상황
- 8개 이상 모듈이 `forwardRef`로 얽힌 순환 의존성: auth ↔ dashboard ↔ stripe ↔ payment-link ↔ subscription ↔ engine
- ProjectController 1,465줄 / ProjectService 972줄 / ProjectRepository 1,689줄의 God Class

### 왜 어려웠나
- `forwardRef`는 증상 은폐일 뿐 — 근본 원인은 공유 데이터 접근의 단일 소유자 부재
- 도메인 간 실제 의존이 얽혀 있어(솔루션 변경 → unit-set 재계산 등) 경계를 잘못 그으면 오히려 악화
- API 호환성을 깨지 않고 40+ 엔드포인트를 이동해야 함

### 해결
1. 공유 repository(AuthRepository, DashboardRepository, PaymentLinkRepository, EngineRepository, SubscriptionDataService)를 모은 `@Global()` **CoreModule** 생성 (`src/core/core.module.ts`)
   - 순환 import 자체를 구조적으로 제거 → `*.module.ts`에서 forwardRef **8+ → 0**
2. 도메인 경계 기준 5개 모듈 분리:
   | 모듈 | 컨트롤러 | 서비스 | 엔드포인트 |
   |------|---------|--------|-----------|
   | project/ (core) | 343줄 | 305줄 | — |
   | solution/ | 585줄 | 251줄 | 18 |
   | unit-set/ | 299줄 | 179줄 | 10 |
   | project-group/ | 192줄 | 147줄 | 7 |
   | building-library/ | 177줄 | 138줄 | 5 |

### 결과
- 모듈 초기화가 결정적(deterministic)으로 변함
- 각 모듈 ≤600줄, 도메인별 독립 수정 가능, 데이터 흐름 추적 용이

### 면접 포인트
- "버그 수정"이 아닌 "아키텍처 패턴 인식" 사례 — forwardRef 남발이라는 증상에서 구조적 원인(소유권 부재)을 진단
- 점진적 마이그레이션(API 호환성 유지) 역량 어필

### 예상 꼬리 질문
- Q. @Global 모듈은 안티패턴 아닌가? → cross-cutting 공유 자원(repository 계층)에 한정 사용. 비즈니스 로직은 각 도메인 모듈에 유지. 무분별한 글로벌화와 구분되는 의도적 트레이드오프
- Q. 도메인 경계는 어떻게 정했나? → 엔드포인트 그룹/데이터 접근 패턴 분석으로 응집도가 높은 단위(solution, unit-set 등) 식별

---

## 🥉 사례 3: Guard의 request body mutation 제거 (코드 품질/설계 안목용)

### 상황
- 인증 guard 8개 전부가 `req.body.decoded_token`에 디코딩된 JWT를 주입
- "동작은 하지만": body가 로그/엔진 payload에 그대로 유출, ValidationPipe와 충돌, 타입 안전성 제로

### 왜 어려웠나
- 에러가 발생하지 않는 결함이라 발견 자체가 어려움
- guard 8개·controller 19개·interceptor들을 동시에 일관되게 변경해야 함
- ValidationPipe `whitelist`가 guard가 기록한 컨텍스트를 제거하는 **실행 순서(타이밍) 이슈**: guard → pipe → param decorator 순서를 정확히 이해해야 해결 가능

### 해결
1. `src/common/types/express.d.ts`로 Express Request 타입 확장 (user, companyIds, deviceId, convertedProjectId, roles)
2. guard가 body가 아닌 `request['user']` 등 request 프로퍼티에 기록
3. `@CurrentUser`, `@CompanyIds`, `@DeviceId`, `@ConvertedProjectId` 커스텀 데코레이터로 추출
4. ValidationPipe에 `whitelist: true, forbidNonWhitelisted: true` 적용 → body 오염 자동 차단

### 결과
- `decoded_token` 참조 0건, 19개 컨트롤러 전체 타입 안전한 요청 컨텍스트 확보
- 민감 정보(디코딩된 JWT)의 로그/외부 payload 유출 차단

### 면접 포인트
- "정상 동작하는 코드에서 숨은 결함을 찾는 안목"
- NestJS 실행 라이프사이클(middleware → guard → interceptor → pipe → handler) 이해도

---

## 사례 4: User Role/Permission 시스템 개편 — 정책 기반 권한 모델 (도메인 모델링/설계 역량용)

### 상황 (Situation)
- 기존 권한 체계는 `user_level_constant.authority` 숫자 기반 계층 비교 (`if (userAuthority >= requiredAuthority)`)
- "manager" 역할 신설 + 액션별 세분화된 권한 요구사항 등장 (예: internal은 자기가 만든 프로젝트만 수정, manager는 회사 내 전부)

### 문제 (Problem) — 왜 어려웠나
1. **숫자 계층 모델의 표현력 한계**: "creator만 가능", "owner만 삭제 가능" 같은 **조건부 권한**을 상하 관계로는 표현 불가
2. **모델링 자체가 논쟁 지점**: manager를 capability flag(`canManageSeat`)로 둘지, 독립 user_level로 둘지 — flag 방식은 seat/account 관리 권한 경계가 모호해짐
3. 코드 곳곳에 흩어진 권한 분기를 깨지 않고 단일 결정 지점으로 모아야 함
4. 정책 변경 시 배포 없이 반영되어야 함 (운영팀 요구)

### 해결 (Action)
1. **`permission_policy` 테이블 도입**: `(action, user_level_id) → require_condition` 매트릭스
   - `action`: `project.delete`, `solution.edit`, `seat.manage` 등 도메인 액션 단위 (~23개)
   - `require_condition`: `NULL`(무조건 허용) / `'creator'` / `'owner'` / `'self'` — 조건부 권한을 데이터로 표현
   - unique constraint `(action, user_level_id)`로 정책 무결성 보장
2. **manager를 capability flag가 아닌 1급 user_level로 결정**: external / internal / manager / admin / developer 5단계 — 권한 결정 축을 하나로 유지 (flag 조합 폭발 방지)
3. **권한 결정을 단일 지점으로 집중**: PermissionService가 policy 테이블 기준으로 판정, 5분 TTL 캐시로 정책 변경 hot-reload (서버 재시작 불필요)
4. **FE/BE 책임 분리**: FE는 user_level을 직접 해석하지 않고 BE가 계산해준 **capability 플래그만 소비** → 정책 변경 시 FE 배포 불필요
5. **부속 시스템**: `company_user_rel.is_allowed`(allowlist), `company_allow_list_log`(감사 로그), allowlist 정원 체크는 `SELECT ... FOR UPDATE` 회사 row 락으로 동시성 제어

### 결과 (Result)
- 권한 규칙이 코드 분기에서 **데이터(정책 테이블)로 이동** → 신규 액션 추가가 SQL seed 한 줄
- 액션 × 레벨 × 조건 매트릭스로 기획팀과 같은 언어로 권한 논의 가능
- 정책 변경이 배포 없이 5분 내 반영

### 면접 포인트
- RBAC의 한계(조건부 권한)를 인식하고 **policy table + condition** 하이브리드로 확장한 설계 판단
- "capability flag vs 1급 role"이라는 모델링 트레이드오프를 명시적으로 검토한 과정
- 권한이라는 cross-cutting concern을 단일 결정 지점으로 수렴시킨 구조

### 예상 꼬리 질문
- Q. 왜 Casbin/CASL 같은 라이브러리를 안 썼나? → 필요한 표현력이 "액션 × 레벨 × 소유 조건" 매트릭스로 한정적. 범용 정책 엔진은 학습/운영 비용 대비 과잉, 정책을 기획팀과 공유 가능한 단순 테이블로 유지하는 게 우선
- Q. creator/owner 조건은 어디서 검증하나? → 정책 조회(레벨×액션)와 리소스 소유권 확인을 분리. 가드/서비스에서 리소스의 creator_id와 요청 유저를 대조
- Q. 권한 캐시 무효화는? → 정책은 저빈도 변경이라 5분 TTL 만료 방식으로 충분 — 즉시 무효화 복잡도를 의도적으로 회피

---

## 사례 5: Floating Seat 대기열 — Redis 기반 분산 동시성 제어 (동시성/분산시스템용)

> 📖 상세 메커니즘(Lua 스크립트 코드, race 시나리오, TTL 설계 근거, 꼬리 질문 심화)은 [floating-seat-deep-dive.md](./floating-seat-deep-dive.md) 참조

### 상황 (Situation)
- 회사별 동시 사용 좌석 수를 제한하는 floating license 모델 도입 (`max_seat_count`)
- 좌석이 가득 차면 FIFO 대기열에 진입, 빈자리가 나면 순서대로 할당
- 대기자가 현재 점유자에게 좌석 양보 요청을 보내는 기능 포함

### 문제 (Problem) — 왜 어려웠나
1. **분산 동시성**: 다중 인스턴스 환경에서 마지막 1좌석을 두 명이 동시에 잡으려 할 때 정원 초과를 막아야 함 — DB 락은 로그인 hot path에 부적합
2. **"좌석 점유 ≠ 소켓 연결"이라는 상태 모델**: 탭 여러 개, 새로고침, 일시적 네트워크 끊김에도 좌석은 유지되어야 하고, 진짜 이탈일 때만 회수되어야 함
3. **유령 대기자(ghost waiting)**: 대기열에 넣어두고 브라우저를 닫은 유저가 영원히 자리를 차지하는 문제
4. **타임아웃 계층이 많음**: 소켓 끊김 유예, WS 바인딩 실패, 양보 요청 미응답, ACK 미수신 — 각각 다른 시간 척도의 비동기 만료 처리 필요
5. **디바이스 정책**: 1 user = 1 device 강제, 다른 기기 로그인 시 기존 기기 강제 퇴출 + 토큰 무효화

### 해결 (Action)
1. **Redis를 단일 진실 원천으로**: 점유는 `seat:company:{id}:occupants` SET (SCARD = 현재 점유 수), 대기열은 LIST(FIFO), 소켓은 `seat:user:{id}:sockets` SET — 상태별 키 분리 (~14종)
2. **Lua 스크립트로 check-and-set 원자화** (`seat.repository.ts`):
   - `TRY_ACQUIRE`: 멱등 체크(SISMEMBER) → 정원 체크(SCARD) → SADD를 단일 원자 연산으로 → 동시 로그인 race에서 정원 초과 원천 차단
   - `TAKEOVER_INACTIVE`: 비활성 점유자 좌석을 대기자가 가져갈 때, "대상이 여전히 점유 중이고 소켓이 비어있는" 조건 검사와 swap을 원자화 — 대상이 그 사이 재접속하면 `target_active`로 실패 반환
   - `ASSIGN_WAITING`: 매니저의 대기열 강제 할당 (LREM + SADD 원자화)
3. **상태 머신 설계**: 점유(occupant) / 활성(active, 소켓 보유) / 유예(grace, 10초 TTL) / 대기(waiting)를 분리 — 마지막 소켓이 끊겨도 grace를 거쳐 "비활성 점유"가 될 뿐 좌석은 유지, 회수는 명시적 이벤트(로그아웃·강제 해제·양보·takeover)로만
4. **Bull 지연 잡으로 타임아웃 계층 처리**: grace 만료(10s), WS 바인딩 실패(30s), 양보 요청 미응답 강제 퇴출(120s), ACK 미수신 fast-kick(5s)
5. **유령 대기자 정리**: 폴링이 갱신하는 presence 마커(10s TTL) + `pruneDeadWaiting`으로 죽은 대기자 제거
6. **디바이스 강제 교체**: 퇴출된 deviceId를 `revoked_devices` SET에 기록 (TTL = JWT refresh 수명 14일) → 인증 가드가 매 요청 검사해 구 기기 토큰 무효화
7. **점진 도입**: `company_user_rel.is_seat_managed` 플래그로 좌석 관리 대상자만 적용, 기존 유저는 bypass — 빅뱅 전환 회피

### 결과 (Result)
- DB 락 없이 Redis 원자 연산만으로 다중 인스턴스 환경의 좌석 정원 보장
- 새로고침/멀티탭/순단에도 좌석이 유지되는 안정적 UX + 진짜 이탈은 자동 회수
- 양보 요청 → 수락/타임아웃 → FIFO 재할당의 전체 라이프사이클 자동화

### 면접 포인트
- **분산 환경에서 락 없는 동시성 제어** (Lua 원자 스크립트 = Redis판 CAS) 설계 경험
- "연결"과 "점유"를 분리한 상태 머신 모델링 — 실시간 시스템의 흔한 함정(끊김 = 이탈 오판)을 구조적으로 회피
- 5종의 서로 다른 타임아웃을 지연 잡 큐로 일원화한 비동기 만료 설계

### 예상 꼬리 질문
- Q. 왜 DB 락이 아닌 Redis Lua인가? → 좌석 획득은 로그인 hot path. row 락은 커넥션 점유 + 데드락 리스크. Redis 단일 스레드 + Lua 원자성이 마이크로초 단위로 동일 보장 제공
- Q. Redis가 죽으면? → 좌석 상태는 재구성 가능한 휘발성 상태(로그인 시 재획득). 영속 필요 데이터(allowlist, 정책)는 DB에 분리 보관
- Q. takeover 중 대상이 재접속하면? → Lua 스크립트 내에서 "소켓 비어있음" 조건을 swap과 원자적으로 검사 — 재접속이 먼저면 `target_active` 실패로 안전하게 종료
- Q. 설계하면서 발견한 함정은? → 획득은 user 단위 멱등(+1 한 번)인데 해제를 socket 단위(-1 per socket)로 다루면 멀티탭에서 모델 불일치 발생 — 획득/해제의 단위(user vs socket)를 반드시 일치시켜야 한다는 교훈

---

## 보너스: 3-tier 캐시 — UUID→ID 변환 (곁들임용)

- 모든 project-scoped 요청마다 필요한 project UUID→ID 변환 병목 해결
- **in-memory LRU(2000개, 10분 TTL, ~0ms) → Redis(1시간 TTL, ~1ms) → DB(~10-50ms)** 3단 폴백
- Redis 기록은 fire-and-forget으로 장애 허용, 접근 제어 캐시는 60~300초 짧은 TTL로 분리
- 위치: `request-project-access.guard.ts` (~192줄)

---

## 면접 유형별 추천

| 면접 유형 | 추천 사례 |
|----------|----------|
| 성능/백엔드 딥다이브 | 사례 1 (JSON 최적화) |
| 시스템 설계 / 시니어 | 사례 2 (순환 의존성 + God Class) |
| 코드 품질 / 설계 안목 | 사례 3 (body mutation 제거) |
| 도메인 모델링 / 설계 판단 | 사례 4 (permission_policy 개편) |
| 동시성 / 분산 시스템 | 사례 5 (floating seat 대기열) |
| 캐싱/인프라 곁들임 | 보너스 (3-tier 캐시) |
