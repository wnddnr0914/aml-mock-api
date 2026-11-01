# 기존 Render 서비스를 GNN 전용 Mock으로 교체하기

기존 GitHub 저장소 `wnddnr0914/aml-mock-api`와 Render 서비스 `aml-mock-api`를 그대로 업데이트한다.
기존 서비스 주소는 [https://aml-mock-api.onrender.com](https://aml-mock-api.onrender.com)이다.

이번 버전은 **거래 ID를 받으면 고정 의심 점수를 반환하는 GNN 대체 API**다.
요청 한 번에 결과를 바로 반환하며, 분석 작업 등록·상태 조회·거래망 추출·GNNExplainer·보고서 생성은 포함하지 않는다.

## 1. 새 파일을 GitHub에 올리기

1. 전달받은 `gnn-mock-api.zip`의 압축을 푼다.
2. 압축을 푼 폴더 안으로 들어가 `main.py`, `golden_case.json`, `requirements.txt`, `render.yaml`이 보이는 위치를 찾는다.
3. [기존 GitHub 저장소](https://github.com/wnddnr0914/aml-mock-api)를 열고 **Add file → Upload files**를 누른다.
4. 새 폴더 **안의 파일·폴더들**을 업로드 영역에 끌어다 놓는다. 기존 이름의 파일은 새 내용으로 덮어쓴다.
5. 커밋 메시지를 `Replace pipeline mock with GNN-only mock`으로 입력하고 **Commit changes**를 누른다.
6. 저장소 첫 화면에서 `main.py`와 `golden_case.json`이 바로 보이는지 확인한다. 새 `gnn-mock-api` 폴더를 한 겹 더 만들어 그 안에 넣지 않는다.

새 실행 코드는 `main.py`를 기준으로 시작한다. 이전 `models.py`, `pipeline.py`, `store.py` 등이 저장소에 남아 있어도 새 코드가 가져오지 않으면 실행에 사용되지 않는다.
새 ZIP에 없는 이전 전용 파일은 비교 후 정리할 수 있지만, 재배포를 위해 먼저 삭제할 필요는 없다.

## 2. 기존 Render 서비스 재배포

1. [Render 대시보드](https://dashboard.render.com/)에서 기존 웹서비스 **aml-mock-api**를 연다.
2. 왼쪽 **Environment**에서 기존 `API_KEY` 값이 있는지 확인한다. 기존 키를 그대로 사용한다.
3. **Deploys → Manual Deploy → Deploy latest commit**을 선택한다.
4. 방금 올린 GitHub 커밋으로 배포가 시작되는지 확인하고 **Live**가 될 때까지 기다린다.

같은 서비스의 코드를 교체하는 작업이므로 **New Blueprint나 새 Web Service를 만들 필요가 없다.**
`render.yaml`의 서비스 이름도 기존과 같은 `aml-mock-api`다.
**Deploy latest commit**은 서비스에 연결된 브랜치의 최신 커밋을 배포하는 메뉴다. [Render 공식 배포 안내](https://render.com/docs/deploys#manual-deploys)

새 앱은 SQLite·작업 큐를 사용하지 않는다. 이전 환경변수 `DATA_DIR`, `MOCK_STAGE_DELAY_SECONDS`가 남아 있어도 새 코드가 사용하지 않는다.
`CORS_ORIGINS`는 계속 사용하므로 실제 프론트엔드 주소가 이미 등록돼 있다면 유지한다.

## 3. 새 API 확인

1. [서버 상태](https://aml-mock-api.onrender.com/healthz)를 열어 정상 응답을 확인한다.
2. [Swagger](https://aml-mock-api.onrender.com/docs)를 열고 브라우저를 새로고침한다.
3. 업무 API 목록이 **POST `/api/v1/detect` 하나**인지 확인한다. 이전 `/api/v1/runs` 세 개가 보이면 아직 이전 버전이 배포됐거나 화면이 갱신되지 않은 것이다.
4. **Authorize**에서 기존 `API_KEY` 값을 입력한 뒤 **Authorize → Close**를 누른다.
5. **POST `/api/v1/detect` → Try it out**을 누르고 다음 내용을 입력한다.

```json
{
  "tx_ids": ["TX_99201"],
  "threshold": 0.8
}
```

**Execute**를 눌러 HTTP **200** 응답과 다음 핵심 값을 확인한다.

- `is_mock`: `true`
- `model_version`: `gnn-mock-v1`
- `predictions[0].tx_id`: `TX_99201`
- `predictions[0].anomaly_score`: `0.94`
- `predictions[0].is_detected`: `true`

이제 `run_id`를 복사하거나 상태를 반복 조회하지 않는다. POST 응답 자체가 예측 결과다.
임계값을 `0.95`로 바꿔 다시 실행하면 같은 거래의 점수는 `0.94`로 유지되고 판정은 `false`가 된다.

## 4. 팀원에게 변경 내용 전달

API 기본 주소와 기존 API 키는 그대로 전달한다. 호출 규격이 바뀌었으므로 팀원 코드는 다음처럼 변경한다.

| 항목 | 새 규격 |
|---|---|
| 요청 | `POST /api/v1/detect` |
| 인증 | `X-API-Key` 헤더에 기존 팀 개발 키 |
| 본문 | `tx_ids` 목록, 선택적으로 `threshold` |
| 응답 | 요청한 각 거래의 점수·임계값 판정 |
| 원본 시연 거래 | 배포 파일의 `golden_case.json`을 공통 fixture로 사용 |

거래망 추출·표시와 보고서 생성은 각 담당 모듈에서 구현한다. 이 Mock의 점수는 원본 거래 ID에 연결해 사용할 수 있다.
실제 GNN으로 교체할 때도 모델은 해당 거래와 그래프·특징에 접근해야 한다. 거래 ID 자체가 GNN의 학습 입력이라는 의미는 아니다.

Render Free는 요청이 15분간 없으면 절전하고 다음 접속에서 약 1분의 재개 시간이 걸릴 수 있다.
이번 버전은 실행 기록을 저장하지 않고 소스에 포함된 고정 fixture를 사용한다. [Render Free 공식 제한](https://render.com/docs/free)
