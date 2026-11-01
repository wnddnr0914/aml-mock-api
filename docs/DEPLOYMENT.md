# Mock API 실행·배포 안내

이 서버를 실행하면 GNN·GPU·IBM 원본 데이터·LLM 키 없이 팀원들이 분석 화면과 보고서 입력을 연동할 수 있다. 먼저 로컬에서 확인한 뒤 팀 공용 URL이 필요하면 Render에 올린다. 이 문서는 배포 방법이며, 실제 클라우드 서비스 생성·게시를 수행한 상태는 아니다.

## 1. Windows에서 내 컴퓨터로 실행

Python 3.13을 설치한 뒤 PowerShell에서 다음 명령을 순서대로 실행한다. 가상환경을 활성화하지 않고 실행하므로 PowerShell 실행 정책을 바꿀 필요가 없다.

```powershell
Set-Location -LiteralPath 'C:\Users\신중욱\Documents\ChatGPT\P실무 프로젝트\aml-mock-api'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

브라우저에서 [Swagger UI](http://127.0.0.1:8000/docs)를 연다. `POST /api/v1/runs`의 **Try it out → Execute**로 예제 요청을 보내고 반환된 `run_id`를 복사한다. `GET /api/v1/runs/{run_id}`에서 상태를 조회한다. 완료되면 `GET /api/v1/runs/{run_id}/results`를 호출한다. 서버 종료는 실행 창에서 `Ctrl+C`다.

기본 저장 위치는 `data/mock.db`다. 같은 디스크를 유지한 채 서버를 다시 시작하면 완료 기록이 남는다. 중단 당시 대기·실행 중이던 작업은 시작 시 실패로 정리되므로 새 요청으로 다시 실행한다. 개발 코드 자동 재시작을 원하면 로컬에서만 `--reload`를 사용할 수 있지만, 저장 중인 실행도 중단될 수 있다.

## 2. 팀원이 같은 네트워크에서 접속

같은 Wi-Fi/LAN에 연결된 팀원에게 잠시 공유할 때 사용할 수 있다. 서버 PC가 켜져 있고 서버 프로세스가 실행 중이어야 한다.

1. 서버를 종료하고 아래 명령으로 다시 시작한다. 키는 이번 PowerShell 세션의 환경변수에 저장된다.

   ```powershell
   $env:API_KEY = (& .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(32))')
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
   ```

2. 별도 PowerShell에서 `ipconfig`로 서버 PC의 Wi-Fi/이더넷 **IPv4 주소**를 찾는다. 예를 들어 `192.168.0.25`라면 팀원 접속 주소는 `http://192.168.0.25:8000/docs`다. `0.0.0.0`은 접속 주소로 사용하지 않는다.
3. Windows 방화벽 알림이 뜨면 신뢰하는 **개인 네트워크**에서 Python 연결을 허용한다. 이미 차단됐다면 Windows 보안 → 방화벽 및 네트워크 보호 → 고급 설정에서 개인 네트워크의 TCP 8000 인바운드만 허용한다. 학교·회사 네트워크의 기기 간 통신 제한은 네트워크 관리자 설정에 따른다.
4. 서버를 실행한 첫 번째 PowerShell에서 `$env:API_KEY`로 키를 확인해 팀 내부에 전달한다. Swagger의 **Authorize**에 키 값만 입력한다. 코드에서는 `X-API-Key` 헤더에 담는다.
5. 프론트엔드의 API 주소를 위 LAN 주소로 바꾼다. 프론트엔드가 팀원 PC의 `http://localhost:5173`에서 실행된다면 기본 CORS 설정을 쓸 수 있다. 프론트엔드도 LAN 주소로 연다면 그 **프론트엔드 주소**를 `CORS_ORIGINS`에 추가한 뒤 서버를 재시작한다.

LAN HTTP 공유는 신뢰하는 개발망에서 사용한다. 다른 장소에서도 접속해야 한다면 아래 HTTPS 배포를 사용한다.

## 3. Render에 올려 팀 공용 HTTPS URL 만들기

Render 계정과 본인의 GitHub 저장소가 필요하다. 아래 두 방법 중 하나만 사용한다. 이 프로젝트에 Render 설정 파일을 포함했으므로 A 방식으로 시작하기 쉽다.

### 먼저 GitHub 저장소 준비

GitHub에서 새 저장소 `aml-mock-api`를 만든다. 프로젝트 전체 작업 폴더 대신 **이 `aml-mock-api` 폴더의 소스만** 올린다. `main.py`, `requirements.txt`, `render.yaml`이 저장소 최상위에 보여야 한다. 함께 제공한 모듈·문서·예제·스크립트도 포함한다. `.venv`, `data`, `.env`, DB 파일, 실제 API 키는 업로드하지 않는다.

GitHub 웹의 **Add file → Upload files** 또는 GitHub Desktop으로 올릴 수 있다. 폴더째 올려 `aml-mock-api/main.py`처럼 한 단계 안에 들어갔다면, B 방식의 **Root Directory**를 `aml-mock-api`로 지정한다. A 방식에서는 `render.yaml`을 저장소 루트로 옮기고 서비스의 `rootDir: aml-mock-api` 설정을 추가해야 하므로, 처음에는 소스를 최상위에 두는 구성이 간단하다.

### A. 포함된 render.yaml로 생성

1. [Render 대시보드](https://dashboard.render.com/)에 로그인하고 **New → Blueprint**를 선택한다.
2. GitHub 연결을 승인하고 위 저장소를 선택한다. 조직 저장소라면 해당 조직의 설치 권한도 필요하다.
3. `render.yaml`이 있는 브랜치와 파일 경로를 확인한다. 서비스 이름이 이미 사용 중이면 YAML의 `name`을 고유하게 바꾼다.
4. 생성 화면에서 **Free** 서비스와 환경변수 목록을 확인하고 배포한다. `API_KEY`는 `generateValue: true` 설정으로 Render가 생성한다. 요금·사용량 정책은 생성 화면에서 확인한다. 이 파일에는 유료 디스크를 선언하지 않았다.
5. 서비스 **Events/Deploys/Logs**에서 빌드·시작이 끝나고 **Live**가 되는지 확인한다. 자동 배포는 `off`로 설정했으므로 이후 소스 변경은 **Manual Deploy → Deploy latest commit**으로 반영한다.
6. **Environment**에서 생성된 `API_KEY` 값을 확인해 팀 내부에 전달한다. 로그나 GitHub에 키를 남기지 않는다. 환경변수 변경은 저장 후 재배포해야 반영된다.

Blueprint는 저장소의 YAML을 읽어 서비스와 환경변수를 구성하며, `generateValue`는 아직 없는 환경변수에 임의의 비밀값을 생성한다. [Render Blueprint 공식 문서](https://render.com/docs/blueprint-spec)

### B. Web Service 화면에서 직접 생성

1. Render에서 **New → Web Service → Git Provider**를 선택해 GitHub 저장소를 연결한다.
2. 다음 값을 입력한다.

   | 설정 | 입력값 |
   |---|---|
   | Name | 팀에서 구분할 이름, 예: `aml-mock-team2` |
   | Language / Runtime | Python 3 |
   | Branch | 소스를 올린 브랜치 |
   | Root Directory | `main.py`가 저장소 루트라면 비움 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` |
   | Instance Type / Plan | 우선 Free; 생성 화면의 한도 확인 |
   | Health Check Path | `/healthz` |

3. **Environment / Advanced**에서 다음 변수를 추가한다.

   | 변수 | 값과 의미 |
   |---|---|
   | `PYTHON_VERSION` | `3.13.7` — 로컬 확인 환경과 일치 |
   | `API_KEY` | Render의 **Generate**로 만든 임의의 긴 값 |
   | `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173`와 실제 프론트 주소 |
   | `DATA_DIR` | `./data` — 앱 작업 폴더 아래 임시 저장 |
   | `MOCK_STAGE_DELAY_SECONDS` | `0.6` — Mock 단계별 지연 |

4. **Create Web Service**를 눌러 배포한다. Runtime이 Docker로 자동 선택되었다면 위 표대로 Python으로 바꾼다. 서비스 URL은 Live 후 화면 상단에 나온다.

공개 요청을 받으려면 앱은 `0.0.0.0`에 바인딩하고 플랫폼이 전달하는 `$PORT`를 사용해야 한다. 위 빌드·시작 명령은 이 규칙을 반영했다. [Render FastAPI 배포 안내](https://render.com/docs/deploy-fastapi), [Web Service 안내](https://render.com/docs/web-services)

Render는 완전한 패치 버전을 지정하는 `PYTHON_VERSION` 환경변수를 지원한다. 기본 Python 버전이 변해도 위 설정을 사용한다. [Python 버전 설정](https://render.com/docs/python-version)

### 배포 후 연결 확인

예를 들어 Render가 발급한 서비스 주소가 `https://aml-mock-team2.onrender.com`이면 다음 경로를 쓴다. 이 주소는 예시이며 실제 서비스 화면의 주소로 바꾼다.

- `/healthz`: 브라우저에서 서버 응답 확인. 인증 없는 운영 점검용이며 Swagger의 업무 API 목록에는 숨겨져 있다.
- `/docs`: Swagger **Authorize**에 `API_KEY` 값만 입력하고 3개 API를 순서대로 실행.
- `/openapi.json`: 팀원이 내려받을 수 있는 기계 판독용 API 명세.

프론트엔드의 API 기본 주소에 실제 Render 주소를 넣는다. `X-API-Key`를 모든 업무 API 요청에 넣고 JSON 요청에는 `Content-Type: application/json`도 설정한다. `/docs`와 `/openapi.json`은 공개되어 있으며 업무 API는 설정한 키로 보호된다. 브라우저에서 쓰는 팀 공용 키는 개발자가 확인할 수 있는 개발용 접근제어다. 실제 사용자별 권한 체계는 별도 구현한다.

프론트엔드를 웹에 배포했다면 Render의 `CORS_ORIGINS`에 **프론트엔드의 Origin**을 추가한다. 예: `http://localhost:5173,https://team2-ui.example.com`. 경로나 마지막 `/` 없이 스킴·호스트·포트만 적는다. API 서버 주소를 추가하는 설정이 아니다. Origin은 프로토콜·호스트·포트 조합이므로 `localhost`와 `127.0.0.1`도 별개다. [FastAPI CORS 문서](https://fastapi.tiangolo.com/tutorial/cors/)

## 4. 실행 기록을 유지하려면

Free 웹 서비스는 15분 동안 들어오는 요청이 없으면 중지되고, 다음 요청에서 다시 시작하는 데 약 1분이 걸릴 수 있다. 중지·재시작·재배포 때 로컬 SQLite 파일도 없어지므로 예전 `run_id`가 404가 될 수 있다. 시연 직전에 `/docs`를 열고 새 분석을 실행한다. 현재 무료 사용량·빌드·대역폭 한도는 계정의 Billing에서 확인한다. [Render Free 제한](https://render.com/docs/free)

기록 보존이 필요하면 서비스의 유료 Compute Plan과 Persistent Disk 비용을 확인한 뒤 다음처럼 구성한다.

1. 서비스 **Disks → Add Disk**에서 마운트 경로를 `/var/data`로 지정한다.
2. `DATA_DIR`를 기본값 `./data`에서 `/var/data`로 변경한다. Blueprint로 관리한다면 `render.yaml`도 함께 수정한다. 마운트 경로 아래의 `mock.db`만 보존된다.
3. 인스턴스 수와 Uvicorn worker 수는 **각각 1**로 유지한다. 이 구현은 프로세스 안에 작업 큐를 두므로 여러 worker/인스턴스로 늘리지 않는다.
4. 배포·재시작은 진행 중 실행을 중단할 수 있다. DB가 유지되면 중단 실행은 실패로 확인할 수 있고 완료 결과는 다시 조회할 수 있다.

디스크는 유료 서비스에서 사용할 수 있고, 마운트 경로 아래에 쓴 데이터만 재시작·배포 후 유지된다. [Render Persistent Disks](https://render.com/docs/disks)

## 5. Docker로 실행하는 경우

Docker가 설치된 PC/서버에서 프로젝트 폴더를 빌드 컨텍스트로 사용한다.

```powershell
docker build -t aml-mock-api .
$env:API_KEY = (& python -c 'import secrets; print(secrets.token_urlsafe(32))')
docker volume create aml-mock-data
docker run --name aml-mock-api --rm -p 8000:8000 --env API_KEY --env 'CORS_ORIGINS=http://localhost:3000,http://localhost:5173' -v aml-mock-data:/app/data aml-mock-api
```

위 명령은 포그라운드로 실행한다. 종료는 `Ctrl+C`이며 이름 있는 볼륨에 완료 기록이 남는다. 같은 명령으로 다시 시작할 수 있다. `/docs` 접속 주소는 로컬과 같다. 다른 호스트 포트를 쓰려면 예를 들어 `-p 8080:8000`으로 바꾸고 8080으로 접속한다. 이미지를 처음 빌드할 때는 Python 이미지와 패키지를 내려받을 네트워크가 필요하다.

## 6. 자주 발생하는 문제

| 증상 | 확인할 내용 |
|---|---|
| `Could not import module main` | 작업 폴더 또는 Render Root Directory가 `main.py`가 있는 폴더인지 확인 |
| Render에서 포트를 찾지 못함 | `--host 0.0.0.0 --port $PORT` 사용 여부 확인 |
| `401` | Swagger Authorize 또는 `X-API-Key`에 실제 서버 키를 넣었는지 확인 |
| 브라우저만 CORS 오류 | 프론트엔드 주소가 `CORS_ORIGINS`와 정확히 일치하는지 확인하고 서버 재시작/재배포 |
| 결과 조회가 `409` | 실행 상태를 먼저 확인; 아직 진행 중이거나 실패한 실행의 결과는 받을 수 없음 |
| 예전 실행이 `404` | 잘못된 ID 또는 Free 인스턴스의 임시 저장소 초기화 여부 확인 후 새 실행 |
| 처음 요청이 오래 걸림 | Free 인스턴스 재개 대기 후 다시 확인 |
| 서버가 재시작할 때 작업 실패 | 단일 worker 큐의 중단 처리; 완료 여부를 상태 API로 확인하고 새 실행 |

실제 GNN을 연결할 때는 이 배포 구조의 프로세스 안에서 장시간 학습을 실행하지 않는다. 모델 학습은 별도로 수행하고, 추론·거래망·보고서 모듈을 공통 응답 규격에 맞춰 교체한다.
