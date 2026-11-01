# GNN 추론 전용 Mock API

**GNN이 개발되는 동안 거래별 점수 출력만 대체합니다. 업무 API는 `POST /api/v1/detect` 하나입니다.**
입력은 사용자가 선택한 **거래 ID 목록** 방식이며, 첨부 Quick Demo의 골든 케이스 흐름을 참고했습니다.

이 패키지는 앞서 만든 큰 `aml-mock-api`를 대체할 **새 버전**입니다. 이전 파일은 별도 폴더에 보존했습니다.
현재 배포된 서버는 자동으로 바뀌지 않습니다. [기존 Render에 교체하는 방법](docs/REDEPLOY.md)에 따라 업데이트하세요.

## 입력과 출력

요청:

```http
POST /api/v1/detect
Content-Type: application/json
X-API-Key: 서버에 설정한 팀 개발 키
```

```json
{
  "tx_ids": ["TX_99198", "TX_99199", "TX_99200", "TX_99201"],
  "threshold": 0.8
}
```

응답은 HTTP **200**으로 즉시 반환합니다.

```json
{
  "is_mock": true,
  "model_version": "gnn-mock-v1",
  "threshold": 0.8,
  "predictions": [
    {"tx_id": "TX_99198", "anomaly_score": 0.42, "is_detected": false},
    {"tx_id": "TX_99199", "anomaly_score": 0.63, "is_detected": false},
    {"tx_id": "TX_99200", "anomaly_score": 0.58, "is_detected": false},
    {"tx_id": "TX_99201", "anomaly_score": 0.94, "is_detected": true}
  ]
}
```

- `anomaly_score`는 고정 Mock 의심 점수입니다. GNN을 실행하지 않으며 보정된 범죄 확률도 아닙니다.
- `is_detected`는 **점수 >= threshold**를 코드로 계산한 값입니다. 임계값을 바꿔도 점수는 바뀌지 않습니다.
- 요청한 거래를 **정상·탐지 여부와 관계없이 모두**, 입력 순서대로 반환합니다.
- 예전의 날짜 입력, run_id, 상태 폴링, SQLite 저장은 없습니다. `/api/v1/runs` 경로는 이 버전에서 제공하지 않습니다.

정확한 필드·오류 규칙은 [API 규격](docs/API_SPEC.md), 기계 판독 규격은 [openapi.json](openapi.json)을 참고하세요.

## 팀별 책임

| 담당 모듈 | 역할 | 이번 패키지 |
|---|---|---|
| GNN 추론 | 거래 ID에 대응하는 점수 반환 | **이 자리만 Mock으로 대체** |
| 전처리·데이터 로더 | 원본 거래·노드·엣지 특징 준비 | 실제 담당 모듈에서 구현 |
| 거래망 추출 | 선택 거래 주변을 조회하고 Cytoscape 데이터로 변환 | 포함하지 않음 |
| 모델 설명 | GNNExplainer 등의 중요 엣지 계산 | 포함하지 않음 |
| 보고서 | 사실 집계·LangGraph·초안 생성·검증 | 포함하지 않음 |

대시보드는 점수를 거래 ID로 원본 거래에 연결해 표시하고, 보고서팀은 점수를 여러 근거 중 한 요소로 받습니다.
거래망·설명·보고서용 근거 전체가 GNN의 직접 출력이라고 가정하지 않습니다.

## 골든 케이스 파일

`golden_case.json`은 **직접 만든 합성 데이터**입니다. IBM 원본 사례가 아닙니다.
5개 계좌, 4개 거래(A/B/C → D 각 990만 KRW, D → E 2,900만 KRW)를 담았습니다.
시각은 이 합성 예시에서 UTC로 정했습니다. 실제 IBM 데이터의 시간대에 대한 정의는 아닙니다.

- `nodes`, `transactions`: 팀원이 공유할 원본 형태의 예시 거래망입니다. API 응답에는 포함되지 않습니다.
- `selected_tx_id`: 시연에서 선택할 대표 거래 `TX_99201`입니다.
- `mock_model.scores`: 모델 **출력 대체값**입니다. 모델 입력 특징·학습 정답·GNNExplainer 중요도로 사용하지 않습니다.

자료의 GNNExplainer 중요도와 거래 이상 점수는 다른 개념입니다. 예시의 0.94만 대표 거래 점수로 사용하고,
나머지 거래 점수 0.42/0.63/0.58은 정상·탐지 화면을 시험하기 위해 별도로 정한 값입니다.
거래망·보고서 담당자는 필요하면 이 JSON을 파일로 읽어 독립적으로 개발할 수 있습니다.

## Windows에서 바로 실행

이 폴더에서 PowerShell을 열고 실행합니다. Python 3.13 기준입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

[Swagger](http://localhost:8000/docs)를 열어 **GNN → POST /api/v1/detect → Try it out → Execute**로 시험하세요.
로컬은 `API_KEY`를 생략할 수 있습니다. 키를 설정하려면 서버 실행 전에 `$env:API_KEY='팀 개발 키'`로 지정하고
Swagger의 Authorize에 같은 값을 입력합니다. Render에서는 기존 `API_KEY`를 유지합니다.
인증 없는 점검용 `/healthz`는 Swagger 목록에서 숨겼습니다.

## 실제 GNN으로 교체할 위치

`main.py`의 **`MockPredictor`**가 유일한 모델 대체 지점입니다.
현재 `predict(tx_ids)`는 고정 점수를 조회해 `list[float]`로 반환합니다.
실제 모델 어댑터도 같은 순서·개수의 점수를 반환하도록 구현하면 라우터와 클라이언트의 형태를 유지할 수 있습니다.

실제 모델 연결에는 **서버에서 해당 거래의 원본 그래프·특징·학습된 가중치·전처리 설정을 로딩하는 구현**이 추가로 필요합니다.
거래 ID는 조회 키일 뿐이고, GNN이 ID 문자열만 보고 추론하는 것은 아닙니다.
반환 메타데이터는 실제 `model_version`과 `is_mock=false`로 바꿉니다. 입력 특징에 Mock 점수나 정답 라벨을 넣지 않습니다.

## 검증·규격 재생성

```powershell
python -m unittest discover -s tests -v
python scripts\export_contract.py
python scripts\smoke_test.py --base-url http://localhost:8000
```

테스트는 별도 임시 서버에서 실행합니다. 외부 배포는 [REDEPLOY.md](docs/REDEPLOY.md)의 절차를 따릅니다.
