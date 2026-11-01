# 팀별 연동 및 실제 모델 교체

## 지금 병렬로 작업하는 방법

| 담당 | 바로 시작할 작업 | 입력·출력 |
|---|---|---|
| 대시보드 | 기간 입력, 실행 버튼, 상태 폴링, 목록·그래프·빈 상태·실패 화면 | 3개 API와 `examples/client.ts` |
| 보고서 | 근거 기반 프롬프트, LangGraph, 누락 정보 표시, 사실 검증·검토 UI | `items[i].report_input` |
| 데이터·거래망 | 실제 거래 식별자·계좌 키·통화·시간 정책, 이웃 추출·관찰 패턴 계산 | `Transaction`, `Evidence`, `Graph` 모델 |
| GNN·통합 | 오프라인 학습 및 추론 점수 생성, 실행 파이프라인 연결 | `ScoredTransaction`, 버전 정보 |

최초에는 모두 같은 Mock URL과 예시 JSON을 사용한다. 팀원에게 `run_id`를 하드코딩해 전달하지 않는다.
각자가 새 실행을 등록하거나 유효한 완료 실행을 공유하고, UI의 선택 거래·보고서 근거는 같은 `run_id`에서 가져온다.

## 대시보드

1. `POST /api/v1/runs`가 202를 반환하면 응답의 `run_id`를 현재 실행으로 보관한다.
2. 1초 간격으로 상태를 조회하다가 `succeeded` 또는 `failed`에서 멈춘다. 화면 이동 시 폴링을 취소한다.
3. 성공이면 결과 첫 페이지를 받는다. `has_more`일 때 `next_offset`으로 다음 페이지를 조회한다.
4. `transaction.transaction_id`를 목록 키와 선택 거래 키로 사용한다.
5. `graph.nodes`와 `graph.edges`를 Cytoscape 등에서 변환한다. 엣지의 `source`, `target`은 각각
   `edge.transaction.source.account_id`, `edge.transaction.target.account_id`다.
6. `is_selected`로 현재 거래를 강조하고 `is_detected=false`인 단순 관련 거래를 구분한다.
7. 생략 수, 데이터·모델 버전, Mock 표시, cutoff, 원통화를 표시한다. 계좌 관련성만으로 의심 계좌라고 이름 붙이지 않는다.

새 실행을 누르면 이전 실행의 느린 응답으로 화면이 덮이지 않도록 `AbortController` 또는 현재 run_id 비교를 사용한다.
`examples/client.ts`는 브라우저/TypeScript용 호출·폴링 예시이며 UI 프레임워크 의존성이 없다.
브라우저에 전달한 공용 API 키는 개발자가 읽을 수 있다. 이 합성 연동 단계의 키이며 실제 사용자 인증의 대체재가 아니다.

## 보고서 담당

기본 시작 파일은 `examples/results.json`의 `items[0].report_input`이다. API 접속 전에도 동일 구조로 개발할 수 있다.

```python
import json
from pathlib import Path

sample = json.loads(Path("examples/results.json").read_text(encoding="utf-8"))
report_input = sample["items"][0]["report_input"]
# 예: workflow.invoke(report_input) — 팀의 LangGraph 구현에 전달
```

`evidence.transactions`를 사실 목록으로, `totals_by_currency`와 `patterns`를 코드 계산 근거로 쓴다.
금액 계산에는 `Decimal` 또는 적절한 십진 라이브러리를 사용한다. 생성 문장의 거래 사실은 거래·근거 ID에 연결한다.
`model_explanation`의 중요도는 근거 거래와 별개이며 현재는 고정 Mock이다.
누락 정보를 추정 생성하지 않고 `missing_information`을 추가 입력·확인 항목으로 넘긴다.

보고서 작성·수정·검토·다운로드는 보고서팀의 별도 모듈이다. 이 서버의 `review_status`는 언제나 `not_generated`다.
실제 검토 상태를 저장할 때에는 보고서 ID·버전·수정본·연결 근거를 별도로 설계하고 계약을 함께 확장한다.

## 실제 GNN으로 교체하는 순서

1. **전처리 계약 고정:** IBM 원본 행으로 돌아갈 수 있는 transaction_id, 은행+계좌 키, 송수신 방향,
   반복 거래, 금액·통화, 실제 시간 범위·시간대 정책을 정한다. 현재 표본의 UTC를 IBM 원본에 그대로 붙이지 않는다.
2. **출력 스키마 유지:** `models.py`의 `ScoredTransaction` 형식으로 거래별 점수를 반환하는 추론 어댑터를 만든다.
   `pipeline.py:score_transactions()`의 고정 점수 부분을 교체한다. 학습을 실행 버튼에 연결하지 않는다.
3. **실제 범위 검증:** `models.py`의 `DATA_START`, `DATA_END`, 요청 기본값을 실제 데이터 메타데이터에 맞춘다.
   원본의 송금/수취 금액·통화가 다르다면 두 측면의 필드를 먼저 계약에 추가한다. 현재 amount/currency는 송금 측이며 Mock은 환전이 없다.
4. **거래망 모듈 연결:** `pipeline.py:build_detection()`의 이웃 조회와 패턴 계산을 데이터 담당의 모듈로 교체한다.
   이력·cutoff·홉 정책을 유지하고 실제 데이터에서 화면 생략 전의 집계 범위를 보존한다.
5. **버전·출처 교체:** `Versions`의 실제 dataset/model/preprocessing_version을 넣는다. 모든 경로가 실제 데이터일 때
   `is_mock=false`로 바꾼다. 모델 설명은 실제 실행 결과만 실제 method로 표시하며 아직 없으면 새 계약에서 unavailable 상태를 명시한다.
6. **작업 실행 교체:** 현재 worker는 작은 표본만 처리한다. 실제 CPU/GPU 작업을 이벤트 루프에서 직접 실행하면 조회 API가 막힌다.
   초기에는 별도 단일 배치 프로세스가 DB의 작업을 가져가 상태·결과를 저장하는 방식으로 연결한다.
   다중 인스턴스·내구성 있는 재시도까지 필요해지면 작업 관리와 저장소를 함께 변경한다.
7. **연동 재검증:** API 규격을 재생성하고 화면·보고서팀의 계약 테스트를 실행한다. 특히 cutoff 초과 거래,
   반복 거래, 통화별 합계, 근거 ID, 점수 임계값, 빈 결과, 실패·재시작 처리를 점검한다.

함수 한 곳에 모델만 붙이면 전체 실데이터 서비스가 완성되는 것은 아니다. 추론 외에 데이터 로더·거래망 조회·
저장소·시간대·버전·실행 환경도 실제 정책으로 연결한다. API 경로와 응답 계약을 유지하면 프론트와 보고서 입력 코드는 계속 사용할 수 있다.

`mock_scenario`는 팀의 연동 시험용 옵션이다. 실제 배포에서는 `success`만 허용하도록 검증하거나,
계약 버전을 올려 테스트 옵션을 제거한다. `empty`로 강제된 응답을 모델 성능 평가에 사용하지 않는다.
