"""공유 API 계약. 실제 모델 연결 시에도 이 구조를 유지한다."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

DATA_START = date(2026, 10, 1)
DATA_END = date(2026, 10, 3)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Versions(Contract):
    schema_version: str = "1.0.0"
    is_mock: bool = True
    dataset_version: str = "synthetic-fixture-v1"
    model_version: str = "mock-gnn-v1"
    preprocessing_version: str = "mock-preprocessing-v1"


class RunRequest(Contract):
    start_date: date = Field(default=DATA_START, description="합성 UTC 데이터: 2026-10-01~03")
    end_date: date = DATA_END
    threshold: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    analysis_cutoff: AwareDatetime | None = Field(default=None, description="exclusive. 생략하면 종료일 다음날 00:00 UTC")
    history_days: int = Field(default=1, ge=0, le=3)
    graph_hops: int = Field(default=2, ge=1, le=2)
    max_graph_nodes: int = Field(default=50, ge=2, le=50)
    max_graph_edges: int = Field(default=150, ge=1, le=150)
    mock_scenario: Literal["success", "empty", "failure"] = "success"

    @model_validator(mode="after")
    def validate_period(self):
        if not DATA_START <= self.start_date <= self.end_date <= DATA_END:
            raise ValueError("start_date <= end_date, 지원 기간은 2026-10-01~2026-10-03입니다")
        start = datetime.combine(self.start_date, time.min, timezone.utc)
        end = datetime.combine(self.end_date + timedelta(days=1), time.min, timezone.utc)
        self.analysis_cutoff = self.analysis_cutoff.astimezone(timezone.utc) if self.analysis_cutoff else end
        if not start < self.analysis_cutoff <= end:
            raise ValueError("analysis_cutoff는 조회 시작보다 늦고 종료일 다음날 00:00 UTC 이하여야 합니다")
        return self


class ErrorInfo(Contract):
    code: str
    message: str
    retryable: bool = False


class ErrorResponse(Contract):
    error: ErrorInfo
    status: str | None = None
    details: list[dict] = Field(default_factory=list)


class RunStatus(Contract):
    run_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: Literal["queued", "scoring", "building_evidence", "saving", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    parameters: RunRequest
    versions: Versions = Field(default_factory=Versions)
    error: ErrorInfo | None = None
    status_url: str
    results_url: str


class Account(Contract):
    account_id: str = Field(description="은행 ID와 계좌번호의 조합")
    bank_id: str
    account_number: str


class Transaction(Contract):
    transaction_id: str
    timestamp: AwareDatetime
    source: Account
    target: Account
    amount: Decimal = Field(gt=0, description="송금 원통화 금액. JSON에서는 십진 문자열")
    currency: str
    payment_format: str = "Wire"


class ScoredTransaction(Contract):
    transaction: Transaction
    suspicion_score: float = Field(ge=0, le=1)
    is_detected: bool


class CurrencyTotal(Contract):
    currency: str
    amount: Decimal
    transaction_count: int


class Pattern(Contract):
    kind: Literal["fan_in", "fan_out"]
    account_id: str
    distinct_counterparties: int
    transaction_ids: list[str]


class GraphNode(Account):
    role: Literal["selected_source", "selected_target", "related"]


class GraphEdge(ScoredTransaction):
    is_selected: bool


class Graph(Contract):
    neighborhood_direction: Literal["both"] = "both"
    hops: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int
    omitted_nodes: int
    omitted_edges: int
    truncated: bool


class ExplanationEdge(Contract):
    transaction_id: str
    importance: float = Field(ge=0, le=1)


class Explanation(Contract):
    method: Literal["mock_fixture"] = "mock_fixture"
    is_mock: bool = True
    note: str = "UI 연동용 고정 중요도이며 GNNExplainer 계산 결과가 아닙니다."
    edges: list[ExplanationEdge]


class Evidence(Contract):
    evidence_id: str
    run_id: str
    selected_transaction_id: str
    scope_start: AwareDatetime
    scope_end_exclusive: AwareDatetime
    history_included: bool
    transactions: list[Transaction]
    totals_by_currency: list[CurrencyTotal]
    patterns: list[Pattern]
    aggregation_scope: Literal["full_neighborhood_before_display_limits"] = "full_neighborhood_before_display_limits"


class ReportInput(Contract):
    run_id: str
    evidence_id: str
    selected_transaction_id: str
    versions: Versions = Field(default_factory=Versions)
    analysis_cutoff: AwareDatetime
    threshold: float
    suspicion_score: float
    evidence: Evidence
    model_explanation: Explanation
    missing_information: list[str] = Field(default_factory=lambda: ["reporting_institution", "customer_identity", "transaction_purpose"])
    review_status: Literal["not_generated"] = "not_generated"
    note: str = "합성 근거 입력입니다. 보고서 생성·검토·다운로드는 보고서 담당 모듈에서 구현합니다."


class Detection(ScoredTransaction):
    evidence_id: str
    observed_patterns: list[str]
    graph: Graph
    model_explanation: Explanation
    evidence: Evidence
    report_input: ReportInput


class Summary(Contract):
    dataset_account_count: int
    active_account_count: int
    transaction_count: int
    detected_transaction_count: int
    totals_by_currency: list[CurrencyTotal]


class Results(Contract):
    run_id: str
    status: Literal["succeeded"] = "succeeded"
    versions: Versions = Field(default_factory=Versions)
    parameters: RunRequest
    dataset_timezone: Literal["UTC"] = "UTC"
    generated_at: AwareDatetime
    summary: Summary
    total: int
    offset: int
    limit: int
    has_more: bool
    next_offset: int | None = None
    items: list[Detection]
