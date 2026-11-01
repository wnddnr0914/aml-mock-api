"""GNN 추론 자리만 대체하는 Mock. 실행: python -m uvicorn main:app --port 8000"""
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Body, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

TxId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
FIXTURE_PATH = Path(__file__).with_name("golden_case.json")


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectRequest(DTO):
    tx_ids: list[TxId] = Field(min_length=1, max_length=1000, description="서버에 준비된 거래의 ID. 입력 순서대로 점수를 반환합니다.")
    threshold: Score = Field(default=0.8, description="anomaly_score >= threshold이면 is_detected=true")

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.tx_ids) != len(set(self.tx_ids)):
            raise ValueError("tx_ids에 중복 거래 ID를 넣을 수 없습니다")
        return self


class Prediction(DTO):
    tx_id: TxId
    anomaly_score: Score = Field(description="연동용 고정 의심 점수. 보정된 범죄 확률이 아닙니다.")
    is_detected: bool = Field(description="모델 점수에 임계값을 적용한 후처리 결과")


class DetectResponse(DTO):
    is_mock: bool = True
    model_version: str
    threshold: Score
    predictions: list[Prediction]


class ErrorInfo(DTO):
    code: str
    message: str
    unknown_tx_ids: list[str] = Field(default_factory=list)
    details: list[dict] = Field(default_factory=list)


class ErrorResponse(DTO):
    error: ErrorInfo


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, unknown_tx_ids=None):
        self.status_code = status_code
        self.body = ErrorResponse(error=ErrorInfo(
            code=code, message=message, unknown_tx_ids=unknown_tx_ids or []
        ))


class MockPredictor:
    """실제 모델로 교체할 지점. fixture의 출력용 점수만 읽고, 그래프를 생성하지 않는다."""

    is_mock = True

    def __init__(self, fixture_path: Path):
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.model_version = data["mock_model"]["model_version"]
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("mock_model.model_version은 비어 있지 않은 문자열이어야 합니다")
        self.scores = TypeAdapter(dict[TxId, Score]).validate_python(data["mock_model"]["scores"])
        known_ids = TypeAdapter(list[TxId]).validate_python([row["tx_id"] for row in data["transactions"]])
        if not known_ids or len(known_ids) != len(set(known_ids)) or set(known_ids) != set(self.scores):
            raise ValueError("golden_case.json의 거래 ID와 Mock 점수 ID가 일치해야 합니다")

    def predict(self, tx_ids: list[str]) -> list[float]:
        unknown = [tx_id for tx_id in tx_ids if tx_id not in self.scores]
        if unknown:
            raise ApiError(404, "UNKNOWN_TX_ID", "준비된 골든 케이스에 없는 거래 ID입니다.", unknown)
        return [self.scores[tx_id] for tx_id in tx_ids]


key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(*, fixture_path: Path | None = None, api_key: str | None = None, cors_origins=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.predictor = MockPredictor(fixture_path or FIXTURE_PATH)
        yield

    app = FastAPI(
        title="GNN Inference Mock API", version="2.0.0", lifespan=lifespan,
        description=("GNN 개발 동안 추론 인터페이스만 대체합니다. 거래 ID를 보내면 고정 점수를 즉시 반환합니다. "
                     "원본 그래프 조회·추출, 패턴 분석, GNNExplainer, 보고서 생성은 별도 모듈의 책임입니다. "
                     "API_KEY 설정 시 Authorize에 키 값만 입력하세요."),
    )
    app.state.api_key = os.getenv("API_KEY", "") if api_key is None else api_key
    origins = cors_origins if cors_origins is not None else os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    app.add_middleware(
        CORSMiddleware, allow_origins=[value.strip() for value in origins if value.strip()],
        allow_credentials=False, allow_methods=["POST"], allow_headers=["Content-Type", "X-API-Key"],
    )

    async def authorize(request: Request, supplied: Annotated[str | None, Depends(key_header)]):
        expected = request.app.state.api_key
        if expected and (supplied is None or not secrets.compare_digest(supplied.encode(), expected.encode())):
            raise ApiError(401, "UNAUTHORIZED", "올바른 X-API-Key 헤더가 필요합니다.")

    @app.exception_handler(ApiError)
    async def handle_api_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=exc.body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc):
        details = [{"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()]
        body = ErrorResponse(error=ErrorInfo(code="VALIDATION_ERROR", message="입력 값을 확인하세요.", details=details))
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.post(
        "/api/v1/detect", response_model=DetectResponse, tags=["GNN"],
        summary="거래 ID별 GNN Mock 점수 반환", dependencies=[Depends(authorize)],
        responses={status: {"model": ErrorResponse} for status in (401, 404, 422)},
    )
    def detect(request: Request, body: Annotated[DetectRequest, Body(openapi_examples={
        "golden": {"summary": "골든 케이스 4거래", "value": {
            "tx_ids": ["TX_99198", "TX_99199", "TX_99200", "TX_99201"], "threshold": 0.8,
        }},
        "selected": {"summary": "선택 거래 1건", "value": {"tx_ids": ["TX_99201"], "threshold": 0.8}},
    })]):
        predictor = request.app.state.predictor
        scores = predictor.predict(body.tx_ids)
        return DetectResponse(
            is_mock=predictor.is_mock, model_version=predictor.model_version, threshold=body.threshold,
            predictions=[Prediction(tx_id=tx_id, anomaly_score=score, is_detected=score >= body.threshold)
                         for tx_id, score in zip(body.tx_ids, scores, strict=True)],
        )

    @app.get("/healthz", include_in_schema=False)
    def health():
        return {"status": "ok", "is_mock": app.state.predictor.is_mock}

    return app


app = create_app()
