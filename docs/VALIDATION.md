# 검증 기록

검증일: 2026-11-01 (사용자 시간대 Asia/Seoul).

- Windows / Python 3.13.7, FastAPI 0.141.1, Pydantic 2.13.4, Uvicorn 0.52.3.
- `python -m unittest discover -s tests -v`: 실제 Uvicorn HTTP 통합 테스트 **16개 통과**, 실행 시간 약 18초.
- 정상 완료, 강제·자연 빈 결과, 비동기 실패, 결과 준비 전 409, 인증, CORS, 입력 검증을 확인했다.
- UTC cutoff 경계·임계값 경계·이력 범위·반복 거래 보존·통화별 Decimal 합계를 확인했다.
- 그래프 표시 생략 시 선택 거래 보존과 보고서 전체 근거 유지, 실행 간 근거 분리, 페이지 정렬·누락·중복을 확인했다.
- Idempotency-Key 재사용·충돌, 재시작 후 완료 결과·키 보존, 미완료 작업의 SERVER_RESTARTED 처리를 확인했다.
- `scripts/smoke_test.py`의 success/empty/failure를 각각 실제 HTTP로 실행해 모두 종료 코드 0을 확인했다.
- OpenAPI에 업무 경로가 3개이며 Swagger 예시 3종이 요청 모델 검증을 통과하는지 확인했다.
- OpenAPI와 예시 JSON을 현재 모델에서 다시 생성했다. TypeScript 예제는 타입 제거 후 JavaScript 구문·모듈 로딩을 확인했다.
- Render YAML을 파싱·검사하고 공식 문서 및 구현 환경변수와 대조했다.
- Free 배포의 DATA_DIR는 앱 작업 폴더 아래 `./data`를 사용한다. `/var/data`는 유료 영구 디스크를 해당 경로에 마운트할 때 사용한다.

실제 GNN·GNNExplainer·LLM 호출, IBM 원본 로딩, 보고서 생성, Render 서비스 생성은 실행하지 않았다.
Docker CLI가 없는 환경이므로 실제 이미지 빌드는 확인하지 않았다.

배포 서버에서 다시 확인하려면 다음처럼 실행한다. `API_KEY`는 배포 서버의 실제 값으로 설정한다.

```powershell
$env:API_KEY = '서버에 설정한 팀 개발 키'
python scripts\smoke_test.py --base-url 'https://발급된-서비스.onrender.com'
python scripts\smoke_test.py --base-url 'https://발급된-서비스.onrender.com' --scenario empty
python scripts\smoke_test.py --base-url 'https://발급된-서비스.onrender.com' --scenario failure
```
