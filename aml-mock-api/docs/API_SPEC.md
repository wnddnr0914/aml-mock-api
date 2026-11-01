# API 계약 v1.0.0

이 문서의 경로·필드는 노션 요구를 구현하기 위한 제안 계약이다. 기계 판독 규격은 [`../openapi.json`](../openapi.json),
모든 중첩 필드의 정확한 타입은 Swagger **Schemas** 또는 `models.py`를 기준으로 한다.

## 공통 규칙

- Base URL: 로컬 `http://localhost:8000`, 배포 후 발급된 HTTPS 주소. 모든 업무 경로는 `/api/v1`로 시작한다.
- JSON UTF-8. 요청 본문은 `Content-Type: application/json`.
- `API_KEY`가 설정된 서버에는 `X-API-Key: <팀 개발 키>`가 필요하다. `/docs`, `/openapi.json`, `/healthz`는 공개다.
- ID는 문자열이다. `run_id`는 UUID, `transaction_id`는 합성 원본 행의 고유 ID, 계좌는 `은행ID:계좌번호`다.
- `versions`: `schema_version`, `is_mock`, `dataset_version`, `model_version`, `preprocessing_version`.
- 점수는 0~1의 **의심 점수**다. 보정된 범죄 확률을 의미하지 않는다. `score >= threshold`를 탐지로 선택한다.
- 금액은 JSON **십진 문자열**이다. 원통화 금액을 보존하고 `totals_by_currency`로 나누어 합산한다. 서로 다른 통화를 하나의 합계로 만들지 않는다.
- 결과는 `suspicion_score DESC, transaction_id ASC`로 정렬한다. 완료 후 저장된 결과는 변하지 않는다.
- POST 본문에 정의되지 않은 필드, 잘못된 날짜·범위는 `422`다. GET의 `offset`, `limit`도 범위를 검증한다.

## 1. 분석 실행

`POST /api/v1/runs` → `202 Accepted`

```json
{
  "start_date": "2026-10-01",
  "end_date": "2026-10-03",
  "threshold": 0.8,
  "history_days": 1,
  "graph_hops": 2,
  "max_graph_nodes": 50,
  "max_graph_edges": 150,
  "mock_scenario": "success"
}
```

| 필드 | 기본값 | 검증·의미 |
|---|---|---|
| `start_date` | `2026-10-01` | 조회 시작일, 포함 |
| `end_date` | `2026-10-03` | 조회 종료일, 포함. 시작일 이상, 지원 기간 안 |
| `threshold` | `0.8` | 0 이상 1 이하 |
| `analysis_cutoff` | 종료일 다음날 00:00 UTC | 타임존이 있는 RFC 3339. 시작일 00:00보다 늦고 종료일 다음날 00:00 이하 |
| `history_days` | `1` | 0~3. 조회 시작 이전 관련 거래 이력 |
| `graph_hops` | `2` | 1~2. 선택 거래 양쪽 계좌에서 시작하는 이웃 확장 횟수 |
| `max_graph_nodes` | `50` | 2~50. 화면 표시용 |
| `max_graph_edges` | `150` | 1~150. 화면 표시용 |
| `mock_scenario` | `success` | `success` / `empty` / `failure` |

**지원 데이터는 직접 만든 2026-10-01~03 UTC 24거래다.** 지원 기간 밖의 요청을 자동 보정하지 않는다.
`analysis_cutoff` 생략과 명시적 `null`은 모두 기본값을 사용한다. 오프셋 있는 입력 시각은 UTC로 변환한다.
이 UTC 설정은 해당 합성 표본만의 설정이며 IBM 원본 데이터의 시간대를 주장하지 않는다.

대상 거래 범위는 `[start_date 00:00 UTC, analysis_cutoff)`다.
예를 들어 cutoff `2026-10-01T09:05:00Z`면 09:05 거래는 제외된다.
이력 시작은 `max(데이터 시작, 조회 시작 - history_days)`이며, 이력 조회도 cutoff를 넘지 않는다.
이 Mock은 배치 마감까지 확보된 정보를 사용하는 **기간 회고 분석**이다. 선택 거래 시점 이후라도 cutoff 이전 거래는 근거에 포함될 수 있다.

선택 헤더 `Idempotency-Key`(1~128자)를 같은 요청의 재전송에 사용한다.
같은 키·같은 정규화 본문은 이전 `run_id`를 `202`로 반환한다. 같은 키·다른 본문은 `409 IDEMPOTENCY_CONFLICT`다.
실패한 실행을 재시도할 때는 새 키를 쓴다. 키의 보존 기간은 SQLite 실행 기록과 같다. 키를 생략하면 호출마다 새 실행이다.

응답은 아래 상태 구조이며 `status_url`, `results_url`은 **Base URL에 붙이는 상대 경로**다.
`Location`에는 상태 경로, `Retry-After: 1`에는 권장 재조회 간격(초)이 들어간다.

## 2. 상태 조회

`GET /api/v1/runs/{run_id}` → `200 OK`

```json
{
  "run_id": "복사한 UUID",
  "status": "running",
  "stage": "building_evidence",
  "progress": 50,
  "created_at": "2026-11-01T00:00:00Z",
  "started_at": "2026-11-01T00:00:00Z",
  "finished_at": null,
  "updated_at": "2026-11-01T00:00:01Z",
  "parameters": {"...": "검증·기본값 적용 후 전체 요청"},
  "versions": {"...": "전체 버전 정보"},
  "error": null,
  "status_url": "/api/v1/runs/복사한 UUID",
  "results_url": "/api/v1/runs/복사한 UUID/results"
}
```

위는 필드를 설명한 축약 예시이며 `...` 필드는 실제 응답에 없다. 완전한 JSON 구조는 OpenAPI에서 확인한다.
실행 시각은 서버 UTC 시각으로, 합성 거래 날짜와 구별한다.

| status | stage | progress | 프론트 동작 |
|---|---|---:|---|
| `queued` | `queued` | 0 | 대기 표시, 1초 뒤 재조회 |
| `running` | `scoring` | 10 | 실행 표시 |
| `running` | `building_evidence` | 50 | 근거 조립 표시 |
| `running` | `saving` | 90 | 저장 표시 |
| `succeeded` | `completed` | 100 | 폴링 종료, 결과 조회 |
| `failed` | `failed` | 마지막 값 | 폴링 종료, `error` 표시 |

진행률은 **시연용 단계 값**이며 실제 처리 건수의 비율은 아니다. 기본 단계 지연은 각 0.6초다.
단일 worker이므로 동시 제출은 큐에서 순서대로 처리하며 대기 시간은 별도다.
실패는 `error: {code, message, retryable}`로 설명한다. 같은 DB를 유지한 서버 재시작 시 미완료 실행은
`SERVER_RESTARTED`로 실패 처리한다. 자동 재개·자동 재시도는 하지 않는다.

## 3. 결과 조회

`GET /api/v1/runs/{run_id}/results?offset=0&limit=20` → 성공 완료 시 `200 OK`

| 쿼리 | 범위 | 기본값 |
|---|---|---:|
| `offset` | 0 이상 | 0 |
| `limit` | 1~100 | 20 |

완전한 예시는 [`../examples/results.json`](../examples/results.json)이다.
이 파일은 기본 요청의 첫 탐지 1건을 담은 페이지이며 실제 API 호출 결과로 생성할 수 있는 스키마를 사용한다.

| 응답 필드 | 의미 |
|---|---|
| `run_id`, `status`, `versions`, `parameters` | 실행·계약·모델·요청을 식별. status는 `succeeded` |
| `dataset_timezone`, `generated_at` | 합성 데이터 시간대와 근거 생성 시각 |
| `summary` | 페이지와 무관한 전체 실행 집계 |
| `total`, `offset`, `limit`, `has_more`, `next_offset` | 탐지 건수·페이지. `next_offset`이 null이면 마지막 페이지 |
| `items` | 이 페이지의 탐지 거래 목록 |

`summary.transaction_count`는 조회 대상 전체 거래 수, `detected_transaction_count`는 선택된 고유 거래 수,
`active_account_count`는 조회 대상에서 송수신한 고유 계좌 수, `dataset_account_count`는 표본 전체 고유 계좌 수다.
`summary.totals_by_currency`는 **조회 대상 전체 거래**의 통화별 합계다.
기본 요청의 결과는 전체 24거래·9계좌·12탐지이며 합계는 USD `17100.93`, EUR `13140.90`이다.
화면은 JSON의 십진 문자열을 사용한다. 거래 수와 탐지 수, 보고서 수는 다른 개념이다.

각 `items[i]` 구조:

| 필드 | 내용 |
|---|---|
| `transaction` | `transaction_id`, `timestamp`, `source`, `target`, `amount`, `currency`, `payment_format` |
| `suspicion_score`, `is_detected` | 고정 Mock 점수, 이 목록에서는 항상 true |
| `observed_patterns` | `fan_in`, `fan_out` 또는 빈 배열. 범죄 확정 분류가 아님 |
| `evidence_id` | 해당 실행·선택 거래에 고정된 근거 식별자 |
| `graph` | 화면용 계좌 노드·개별 거래 엣지와 생략 수 |
| `model_explanation` | 실제 모델 설명과 구별한 Mock 중요도 |
| `evidence` | 화면 표시 한도 적용 전의 전체 관련 거래·통화별 합계·관찰 지표 |
| `report_input` | 보고서 담당자가 그대로 받을 실행·버전·점수·전체 근거 묶음 |

계좌 객체는 `{account_id, bank_id, account_number}`다. 은행이 다른 같은 번호를 합치지 않는다.
거래 엣지 ID는 `transaction_id`이므로 같은 계좌 쌍의 여러 거래도 유지한다.

`graph.nodes[*].role`은 `selected_source`, `selected_target`, `related`다.
`graph.edges[*]`는 `transaction`, `suspicion_score`, `is_detected`, `is_selected`를 갖는다.
`source → target` 방향을 화면에 그린다. `is_detected=false`인 관련 거래도 표시될 수 있다.
선택 거래와 양쪽 계좌는 표시 제한이 작아도 남긴다.
`total_nodes`, `total_edges`는 전체 근거 범위의 수, `omitted_nodes`, `omitted_edges`, `truncated`는 화면 생략 정보다.
최대 노드·엣지는 전체 근거의 양을 제한하는 옵션이 아니다.

거래망은 선택 거래 양쪽 계좌에서 **양방향 이웃을 확장**한 뒤 도달한 계좌 사이의 거래를 포함한다.
엣지 방향은 보존하며 `neighborhood_direction="both"`다. 시간 순서를 따르는 자금 이동 경로를 계산한 것은 아니다.
패턴은 전체 이웃 거래망에서 중심 계좌의 서로 다른 송금인·수취인 수가 3 이상일 때 Fan-in/Fan-out으로 관찰한다.
반복 거래 건수와 서로 다른 상대 계좌 수를 구별한다. 형태가 없으면 빈 배열을 반환한다.

`evidence`는 `run_id`, `selected_transaction_id`, `scope_start`, `scope_end_exclusive`, `history_included`,
`transactions`, `totals_by_currency`, `patterns`를 포함한다. 합계는 근거 안의 고유 거래별로 한 번씩 계산한다.
여러 탐지 거래의 근거가 겹칠 수 있으므로 **items별 합계를 더해 실행 전체 합계로 쓰면 안 된다.**

`model_explanation.method="mock_fixture"`, `is_mock=true`이며 중요도는 UI 테스트값이다.
GNNExplainer를 실행하거나 모델 정확도를 측정하지 않는다. 관찰 패턴과도 별도 정보다.

보고서팀은 `report_input.evidence.transactions`의 거래 ID와 수치를 근거로 생성한다.
`missing_information`의 `reporting_institution`, `customer_identity`, `transaction_purpose`는 확인 필요 항목이다.
이 필드들의 값을 임의 생성하지 않는다. `review_status="not_generated"`이며 보고서 생성·편집·다운로드 API는 이번 3개 API의 범위에 포함되지 않는다.

## 시나리오와 오류

`mock_scenario="empty"`는 선택 거래를 강제로 비워 빈 화면을 시험한다. 조회 전체 거래 수·금액은 유지한다.
`mock_scenario="failure"`는 등록 뒤 비동기로 `MOCK_PIPELINE_FAILED` 상태가 된다.
자연스러운 빈 탐지는 `threshold=1` 또는 거래가 없는 cutoff 범위로도 확인할 수 있다.

업무 API 오류 응답:

```json
{
  "error": {
    "code": "RESULTS_NOT_READY",
    "message": "분석이 끝난 뒤 결과를 조회하세요.",
    "retryable": true
  },
  "status": "running",
  "details": []
}
```

| HTTP | code | 의미 |
|---:|---|---|
| 401 | `UNAUTHORIZED` | 키 누락·불일치 |
| 404 | `RUN_NOT_FOUND` | 실행 ID 없음 |
| 409 | `RESULTS_NOT_READY` | 대기·진행 중. 상태 폴링 계속 |
| 409 | `RUN_FAILED` | 실패 실행의 결과 조회. 상태의 상세 error 확인 |
| 409 | `IDEMPOTENCY_CONFLICT` | 같은 키에 다른 본문 |
| 422 | `VALIDATION_ERROR` | 입력 검증. `details[*]`에 위치·타입·메시지 |

상태 API는 실패한 실행을 조회해도 HTTP 200이며 `status="failed"`와 오류 정보를 반환한다.
`retryable=true`는 재시도 가능한 성격을 뜻하며, 실패 실행이 저절로 재실행된다는 의미는 아니다.
정의되지 않은 URL·허용되지 않은 HTTP 메서드는 프레임워크 기본 오류 형식이다.
