# 검증 기록

검증일: 2026-11-01 (Asia/Seoul).

- Python 3.13.7 / FastAPI 0.141.1 / Pydantic 2.13.4 / Uvicorn 0.52.3.
- `python -m unittest discover -s tests -v`: **13개 통과**. 실제 Uvicorn HTTP 11개와 fixture 검증 2개, 약 7초.
- 골든 케이스 4점수·1탐지, 선택 거래 0.94, 입력 순서, 임계값 동점·0·1 경계를 확인했다.
- 빈·중복·잘못된 ID, 허용 개수 초과, 잘못된 임계값·NaN·추가 필드, 미등록 ID의 전체 요청 거부를 확인했다.
- 인증·키 없는 로컬 실행·CORS, Swagger 업무 API 1개, 이전 runs 경로 404, 추론 전용 응답 필드를 확인했다.
- 잘못된 Mock 점수와 fixture ID 불일치가 시작 단계에서 거부되는지 확인했다.
- `scripts/smoke_test.py`를 실제 임시 서버에서 실행해 4 predictions / 1 detected를 확인했다.
- 제공한 골든 케이스의 노드·거래 수, 송수신 계좌 참조, 양수 금액, JSON 예시·OpenAPI와 Render YAML을 검사했다.
- TypeScript 예제는 타입 제거 후 JavaScript 구문·모듈 로딩을 확인했다.

실제 GNN 추론·학습, 원본 IBM 데이터 로딩, 거래망 추출, GNNExplainer, 보고서 생성은 수행하지 않는다.
기존 GitHub·Render 서비스에 원격 변경을 적용하지 않았다. REDEPLOY.md에 따라 사용자 계정에서 교체 배포한다.
