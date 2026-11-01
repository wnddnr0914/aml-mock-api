# GNN Mock 입출력 계약

## 경로·인증

- 업무 API: **POST `/api/v1/detect`** 하나. 동기 응답, 성공 HTTP 200.
- Swagger: `/docs`, OpenAPI: `/openapi.json`.
- 서버 점검: GET `/healthz` → `{"status":"ok","is_mock":true}`. 인증 없이 조회하고 Swagger에는 숨긴다.
- `API_KEY`가 설정된 서버는 `X-API-Key` 헤더를 요구한다. 설정하지 않은 로컬 서버는 인증을 생략할 수 있다.
- JSON 요청의 `Content-Type`은 `application/json`이다.

## 요청

| 필드 | 타입 | 규칙 |
|---|---|---|
| `tx_ids` | 문자열 배열 | 필수, 1~1000개, 중복 금지. ID는 1~64자 영문·숫자·밑줄·하이픈 |
| `threshold` | 숫자 | 선택, 기본 0.8, 0~1의 유한한 수. 문자열·불리언은 허용하지 않음 |

현재 선택 가능한 거래 ID는 `TX_99198`, `TX_99199`, `TX_99200`, `TX_99201`이다.
ID를 임의로 만들어 보내면 점수를 생성하지 않고 오류를 반환한다.
정의되지 않은 요청 필드(`start_date`, `end_date`, `graph_hops` 등)는 422로 거부한다.

대표 거래 1건만 요청하는 최소 예:

```json
{"tx_ids": ["TX_99201"]}
```

## 성공 응답

```json
{
  "is_mock": true,
  "model_version": "gnn-mock-v1",
  "threshold": 0.8,
  "predictions": [
    {"tx_id": "TX_99201", "anomaly_score": 0.94, "is_detected": true}
  ]
}
```

`predictions`의 순서·개수는 요청한 `tx_ids`와 같다. 거래별 출력은 세 필드뿐이다.
`anomaly_score`는 고정 Mock 의심 점수이고, `is_detected = (anomaly_score >= threshold)`다.
점수의 범위는 0~1이며, 임계값은 점수를 변경하거나 결과 배열을 필터링하지 않는다.
탐지 거래가 없으면 모든 항목의 `is_detected`가 false인 배열을 반환한다. 빈 요청 배열은 오류다.
전체 4거래 요청·응답 파일은 `examples/request.json`, `examples/response.json`으로 제공한다.

이 응답에는 `graph`, `evidence`, `report_input`, `model_explanation`, `pattern_type`, 중요도·서술문이 없다.
실제 GNN으로 교체하면 `is_mock=false`, 실제 `model_version`을 사용하며 입출력 필드 형태는 유지할 수 있다.

## 오류

| HTTP | error.code | 의미 |
|---:|---|---|
| 401 | `UNAUTHORIZED` | API 키 누락·불일치 |
| 404 | `UNKNOWN_TX_ID` | 준비되지 않은 ID가 하나 이상 있음. 전체 요청을 실패시키며 부분 결과를 반환하지 않음 |
| 422 | `VALIDATION_ERROR` | 누락·빈 목록·중복 ID·잘못된 형식·범위·추가 필드 |

```json
{
  "error": {
    "code": "UNKNOWN_TX_ID",
    "message": "준비된 골든 케이스에 없는 거래 ID입니다.",
    "unknown_tx_ids": ["TX_NOT_FOUND"],
    "details": []
  }
}
```

입력 검증 오류의 `details`에는 `loc`(오류 위치), `type`, `message`를 반환한다.
정의되지 않은 URL과 잘못된 HTTP 메서드는 FastAPI 기본 오류 형식으로 반환한다.

## 기존 API와의 차이

이전 `/api/v1/runs` 등록·상태·결과 API 3개를 사용하던 코드는 `/api/v1/detect` 호출로 바꾼다.
202 응답·run_id·상태 폴링 없이, 200 응답의 `predictions`를 바로 사용한다.
이 변경은 기존 클라이언트와 호환되지 않으므로 팀에 새 규격을 전달한 뒤 교체 배포한다.
이번 패키지는 앱 버전 2.0.0이며 경로 접두사는 첨부 설계안에 맞춰 `/api/v1`을 유지했다.
