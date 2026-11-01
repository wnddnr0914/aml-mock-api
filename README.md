# AML Mock API

GNN 학습을 기다리는 동안 대시보드팀과 보고서팀이 병렬로 개발하는 FastAPI 서버입니다.
**코드·API 계약·로컬 실행·배포 설정까지 준비했으며, 외부 서버 배포는 아직 실행하지 않았습니다.**

노션의 [프로젝트 차터](https://app.notion.com/p/402b39b74376816b9e2cda5b182f393b)와
[세부 계획서](https://app.notion.com/p/401b39b7437681b3987ce3e1bdb7204b)의 배치 분석·공통 JSON 요구를 바탕으로 작성했습니다.
API 경로와 세부 필드는 이번에 제안한 **v1 계약**입니다. 기존 노션에 확정된 경로가 있다는 의미는 아닙니다.

## 바로 실행하기 — Windows PowerShell

이 폴더를 터미널에서 열고 실행합니다. Python 3.13 기준입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

가상환경 활성화 없이 실행하므로 PowerShell 실행 정책 변경은 필요하지 않습니다.
브라우저에서 [Swagger UI](http://localhost:8000/docs)를 엽니다.

1. `POST /api/v1/runs`의 **Try it out → Execute**를 누릅니다. 기본 예시 기간을 그대로 사용합니다.
2. 응답의 `run_id`를 복사해서 상태 API에 넣습니다. 보통 약 2초 후 `succeeded`가 됩니다. 여러 요청은 순서대로 처리합니다.
3. 결과 API에 같은 `run_id`를 넣으면 탐지 목록·거래망·근거·보고서 입력이 나옵니다.

다른 터미널에서 한 번에 확인할 수도 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

`API_KEY`를 설정했다면 Swagger의 **Authorize**에 해당 값을 입력합니다. `.env.example`은 참고용이며 자동 로딩하지 않습니다.

## API 3개

| 메서드 | 경로 | 목적 |
|---|---|---|
| POST | `/api/v1/runs` | 분석 등록, 즉시 `202`와 `run_id` 반환 |
| GET | `/api/v1/runs/{run_id}` | 대기·실행·성공·실패 및 진행 단계 조회 |
| GET | `/api/v1/runs/{run_id}/results` | 페이지별 탐지 목록, 거래망, 근거, `report_input` |

상태는 `queued → running → succeeded` 또는 `failed`입니다. 결과 준비 전에는 `409`, 성공한 빈 결과는 `200`과 `items: []`입니다.
서버 점검용 `/healthz`는 Swagger 목록에서 숨겼습니다.

## 팀원에게 전달할 것

- **대시보드 담당:** 서버 주소, API 키(설정 시), [API 규격](docs/API_SPEC.md), [응답 예시](examples/results.json), [연동 코드](examples/client.ts).
- **보고서 담당:** `items[i].report_input`을 LangGraph 입력으로 사용합니다. 내부 `evidence`의 거래·금액·패턴을 근거로 사용합니다. 이번 서버는 보고서를 생성하지 않습니다.
- **모델·데이터 담당:** [실제 모델 연결 안내](docs/INTEGRATION.md)에 따라 `pipeline.py`와 저장소 연결을 교체합니다. 프론트가 사용하는 경로·JSON 계약은 유지합니다.

## 포함한 동작

- 직접 만든 **2026-10-01~03 UTC 합성 거래 24건**, 고정 점수, 임계값 필터. IBM 원본 데이터가 아닙니다.
- 기본 요청: 거래 24건, 탐지 12건. 통화별 합계와 고유 활동 계좌 수는 코드로 계산합니다.
- 계좌 노드·개별 거래 엣지, 반복 거래 보존, Fan-in/Fan-out 관찰, 관련 정상 거래 구분.
- 화면 표시 한도와 보고서용 전체 근거 분리, 거래·근거·실행 ID 연결.
- `mock_scenario`로 `success`, `empty`, `failure` 재현. 중요도 역시 Mock이며 실제 GNNExplainer 출력이 아닙니다.
- SQLite 상태·결과 보관, 재시작 시 미완료 작업 실패 처리, 선택적 API 키와 CORS, `Idempotency-Key` 중복 등록 방지.

## 실행 파일과 문서

| 파일 | 역할 |
|---|---|
| `main.py` | FastAPI 라우터, 인증, 단일 배치 worker |
| `models.py` | 입력·출력 검증과 Swagger 스키마 |
| `fixtures.py` | 고정 합성 거래·점수 |
| `pipeline.py` | 점수 필터, 거래망, 관찰 패턴, 보고서 입력 조립 |
| `store.py` | 실행·결과·중복 키 SQLite 저장 |
| `openapi.json` | 배포 전에도 공유할 수 있는 기계 판독 규격 |
| `docs/API_SPEC.md` | 요청·응답·상태·오류·시간 정책 |
| `docs/DEPLOYMENT.md` | 로컬·LAN·Render·Docker 배포 절차 |
| `docs/INTEGRATION.md` | 실제 GNN·LangGraph로 연결하는 위치 |

## 검증

```powershell
python -m unittest discover -s tests -v
python scripts\export_contract.py
```

테스트는 표준 라이브러리로 별도 서버를 실행하며 테스트용 임시 DB를 사용합니다.
`export_contract.py`는 현재 모델에서 OpenAPI·예시 JSON을 다시 만듭니다.

이 구성은 작은 합성 데이터로 연동하는 단일 인스턴스용입니다. `--workers 1`로 실행하고,
SQLite 파일은 Git에 올리지 않습니다. 실제 GPU 추론은 학습과 분리된 실행 경로와 내구성 있는 작업 관리로 연결합니다.
작은 Mock 작업은 앱 수명주기의 비동기 worker에서 처리합니다. 실제 무거운 연산 분리에 관한 근거는
[FastAPI 공식 안내](https://fastapi.tiangolo.com/tutorial/background-tasks/#caveat)에서 확인할 수 있습니다.
