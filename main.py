"""실행: python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1"""
import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager, suppress
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from models import ErrorInfo, ErrorResponse, Results, RunRequest, RunStatus
from pipeline import build_results, score_transactions, utc_now
from store import Store, canonical_request

log = logging.getLogger("aml_mock")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class ApiError(Exception):
    def __init__(self, http_status, code, message, *, status=None, retryable=False):
        self.http_status = http_status
        self.body = ErrorResponse(error=ErrorInfo(code=code, message=message, retryable=retryable), status=status)


async def worker(app):
    while True:
        run_id = await app.state.queue.get()
        status = RunStatus.model_validate_json(app.state.store.get(run_id)["status_json"])
        try:
            status.status, status.stage, status.progress = "running", "scoring", 10
            status.started_at = utc_now()
            app.state.store.update(status)
            await asyncio.sleep(app.state.stage_delay)
            if status.parameters.mock_scenario == "failure":
                raise ApiError(500, "MOCK_PIPELINE_FAILED", "요청한 Mock 실패 시나리오입니다.", retryable=True)
            all_rows, target = score_transactions(status.parameters)
            status.stage, status.progress = "building_evidence", 50
            app.state.store.update(status)
            await asyncio.sleep(app.state.stage_delay)
            result = build_results(run_id, status.parameters, all_rows, target)
            status.stage, status.progress = "saving", 90
            app.state.store.update(status)
            await asyncio.sleep(app.state.stage_delay)
            status.status, status.stage, status.progress = "succeeded", "completed", 100
            status.finished_at = utc_now()
            app.state.store.complete(status, result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Run failed: %s", run_id)
            status.status, status.stage = "failed", "failed"
            status.finished_at = utc_now()
            status.error = exc.body.error if isinstance(exc, ApiError) else ErrorInfo(
                code="PIPELINE_FAILED", message="분석 중 오류가 발생했습니다. 서버 로그를 확인하세요.", retryable=True
            )
            app.state.store.update(status)
        finally:
            app.state.queue.task_done()


def create_app(*, data_dir=None, stage_delay=None, api_key=None, cors_origins=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(data_dir or os.getenv("DATA_DIR", "./data"))
        app.state.store.fail_interrupted()
        app.state.queue = asyncio.Queue()
        delay = float(os.getenv("MOCK_STAGE_DELAY_SECONDS", "0.6")) if stage_delay is None else stage_delay
        if not 0 <= delay <= 60:
            raise ValueError("MOCK_STAGE_DELAY_SECONDS는 0~60이어야 합니다")
        app.state.stage_delay = delay
        app.state.worker = asyncio.create_task(worker(app))
        yield
        app.state.worker.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.worker
        app.state.store.fail_interrupted()

    app = FastAPI(
        title="AML Mock API", version="1.0.0", lifespan=lifespan,
        description=("GNN 개발 중 대시보드·보고서 병렬 개발용 합성 API. "
                     "지원 기간: 2026-10-01~03 UTC. 실제 GNN·LLM을 호출하지 않습니다. "
                     "API_KEY 설정 시 Authorize에 X-API-Key를 입력하세요. 단일 worker로 실행하세요."),
    )
    app.state.api_key = os.getenv("API_KEY", "") if api_key is None else api_key
    origins = cors_origins if cors_origins is not None else os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in origins if s.strip()],
                       allow_credentials=False, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key"],
                       expose_headers=["Location", "Retry-After"])

    async def authorize(request: Request, supplied: Annotated[str | None, Depends(key_header)]):
        expected = request.app.state.api_key
        if expected and (supplied is None or not secrets.compare_digest(supplied.encode(), expected.encode())):
            raise ApiError(401, "UNAUTHORIZED", "올바른 X-API-Key 헤더가 필요합니다.")

    @app.exception_handler(ApiError)
    async def api_error_handler(request, exc):
        return JSONResponse(status_code=exc.http_status, content=exc.body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc):
        # 예외 객체·입력 전체가 JSON에 섞이지 않도록 안전한 필드만 반환한다.
        details = [{"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()]
        body = ErrorResponse(error=ErrorInfo(code="VALIDATION_ERROR", message="요청 값을 확인하세요."), details=details)
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    errors = {code: {"model": ErrorResponse} for code in (401, 404, 409, 422)}

    def read_run(run_id):
        row = app.state.store.get(run_id)
        if row is None:
            raise ApiError(404, "RUN_NOT_FOUND", "존재하지 않는 run_id입니다.")
        return row, RunStatus.model_validate_json(row["status_json"])

    @app.post("/api/v1/runs", status_code=202, response_model=RunStatus, responses=errors,
              dependencies=[Depends(authorize)], tags=["Batch"], summary="1. 분석 실행 등록")
    async def submit_run(body: Annotated[RunRequest, Body(openapi_examples={
        scenario: {"summary": label, "value": {"start_date": "2026-10-01", "end_date": "2026-10-03",
                    "threshold": 0.8, "analysis_cutoff": None, "mock_scenario": scenario}}
        for scenario, label in [("success", "정상 완료"), ("empty", "탐지 결과 없음"), ("failure", "분석 실패")]
    })], response: Response,
                         idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None):
        normalized = canonical_request(body)
        if idempotency_key:
            existing = app.state.store.get_by_key(idempotency_key)
            if existing:
                if existing["request_json"] != normalized:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "같은 Idempotency-Key에 다른 요청을 보낼 수 없습니다.")
                status = RunStatus.model_validate_json(existing["status_json"])
                response.headers["Location"] = status.status_url
                response.headers["Retry-After"] = "1"
                return status
        run_id = str(uuid4())
        now = utc_now()
        status = RunStatus(run_id=run_id, status="queued", stage="queued", progress=0,
                           created_at=now, updated_at=now, parameters=body,
                           status_url=f"/api/v1/runs/{run_id}", results_url=f"/api/v1/runs/{run_id}/results")
        app.state.store.create(status, idempotency_key, normalized)
        app.state.queue.put_nowait(run_id)
        response.headers["Location"] = status.status_url
        response.headers["Retry-After"] = "1"
        return status

    @app.get("/api/v1/runs/{run_id}", response_model=RunStatus, responses=errors,
             dependencies=[Depends(authorize)], tags=["Batch"], summary="2. 분석 상태 조회")
    async def get_run(run_id: str, response: Response):
        _, status = read_run(run_id)
        if status.status in {"queued", "running"}:
            response.headers["Retry-After"] = "1"
        return status

    @app.get("/api/v1/runs/{run_id}/results", response_model=Results, responses=errors,
             dependencies=[Depends(authorize)], tags=["Batch"], summary="3. 탐지 결과·거래망·보고서 근거 조회")
    async def get_results(run_id: str, offset: Annotated[int, Query(ge=0)] = 0,
                          limit: Annotated[int, Query(ge=1, le=100)] = 20):
        row, status = read_run(run_id)
        if status.status == "failed":
            raise ApiError(409, "RUN_FAILED", "분석이 실패했습니다. 상태 API의 error를 확인하세요.", status="failed", retryable=True)
        if status.status != "succeeded":
            raise ApiError(409, "RESULTS_NOT_READY", "분석이 끝난 뒤 결과를 조회하세요.", status=status.status, retryable=True)
        result = Results.model_validate_json(row["result_json"])
        result.items = result.items[offset:offset + limit]
        result.offset, result.limit = offset, limit
        result.has_more = offset + limit < result.total
        result.next_offset = offset + limit if result.has_more else None
        return result

    @app.get("/healthz", include_in_schema=False)
    async def health():
        with app.state.store.connection() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "is_mock": True}

    return app


app = create_app()
