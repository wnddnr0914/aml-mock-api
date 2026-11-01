"""Mock 연산만 격리한다. 실제 추론·거래망 모듈의 교체 지점."""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fixtures import fixture_transactions
from models import (CurrencyTotal, Detection, Evidence, Explanation, ExplanationEdge,
                    Graph, GraphEdge, GraphNode, Pattern, ReportInput, Results,
                    RunRequest, ScoredTransaction, Summary)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def totals(rows: list[ScoredTransaction]) -> list[CurrencyTotal]:
    amounts = defaultdict(Decimal)
    counts = defaultdict(int)
    for row in rows:
        amounts[row.transaction.currency] += row.transaction.amount
        counts[row.transaction.currency] += 1
    return [CurrencyTotal(currency=c, amount=amounts[c], transaction_count=counts[c]) for c in sorted(amounts)]


def account_ids(rows):
    return {a.account_id for r in rows for a in (r.transaction.source, r.transaction.target)}


def score_transactions(request: RunRequest) -> tuple[list[ScoredTransaction], list[ScoredTransaction]]:
    """실제 모델에서는 고정 점수를 추론 점수로 바꾸고 동일한 계약을 반환."""
    all_rows = fixture_transactions()
    for row in all_rows:
        row.is_detected = row.suspicion_score >= request.threshold
    start = datetime.combine(request.start_date, time.min, timezone.utc)
    target = [r for r in all_rows if start <= r.transaction.timestamp < request.analysis_cutoff]
    return all_rows, target


def neighborhood(anchor, candidates, hops):
    reached = account_ids([anchor])
    for _ in range(hops):
        adjacent = [r for r in candidates if account_ids([r]) & reached]
        reached |= account_ids(adjacent)
    return sorted([r for r in candidates if account_ids([r]) <= reached], key=lambda r: (r.transaction.timestamp, r.transaction.transaction_id))


def patterns(rows):
    found = []
    for kind, center, counterparty in [
        ("fan_in", "target", "source"), ("fan_out", "source", "target")
    ]:
        groups = defaultdict(list)
        for row in rows:
            groups[getattr(row.transaction, center).account_id].append(row)
        for key, group in sorted(groups.items()):
            count = len({getattr(r.transaction, counterparty).account_id for r in group})
            if count >= 3:
                found.append(Pattern(kind=kind, account_id=key, distinct_counterparties=count,
                                     transaction_ids=[r.transaction.transaction_id for r in group]))
    return found


def build_detection(run_id, anchor, all_rows, request):
    start = datetime.combine(request.start_date, time.min, timezone.utc)
    dataset_start = min(r.transaction.timestamp for r in all_rows).replace(hour=0, minute=0, second=0, microsecond=0)
    scope_start = max(dataset_start, start - timedelta(days=request.history_days))
    candidates = [r for r in all_rows if scope_start <= r.transaction.timestamp < request.analysis_cutoff]
    related = neighborhood(anchor, candidates, request.graph_hops)
    anchor_id = anchor.transaction.transaction_id
    # 표시 제한에서도 선택 거래와 양쪽 노드는 보존한다.
    displayed = [anchor]
    displayed_accounts = account_ids(displayed)
    for row in related:
        if row.transaction.transaction_id == anchor_id:
            continue
        expanded = displayed_accounts | account_ids([row])
        if len(expanded) <= request.max_graph_nodes and len(displayed) < request.max_graph_edges:
            displayed.append(row)
            displayed_accounts = expanded
    accounts = {a.account_id: a for r in related for a in (r.transaction.source, r.transaction.target)}
    total_nodes = len(accounts)
    graph = Graph(
        hops=request.graph_hops,
        nodes=[GraphNode(**accounts[key].model_dump(), role=(
            "selected_source" if key == anchor.transaction.source.account_id else
            "selected_target" if key == anchor.transaction.target.account_id else "related"
        )) for key in sorted(displayed_accounts)],
        edges=[GraphEdge(**r.model_dump(), is_selected=r.transaction.transaction_id == anchor_id) for r in displayed],
        total_nodes=total_nodes, total_edges=len(related),
        omitted_nodes=total_nodes-len(displayed_accounts), omitted_edges=len(related)-len(displayed),
        truncated=len(displayed) < len(related),
    )
    observed = patterns(related)
    evidence = Evidence(
        evidence_id=f"{run_id}:{anchor_id}", run_id=run_id, selected_transaction_id=anchor_id,
        scope_start=scope_start, scope_end_exclusive=request.analysis_cutoff,
        history_included=any(r.transaction.timestamp < start for r in related),
        transactions=[r.transaction for r in related], totals_by_currency=totals(related), patterns=observed,
    )
    explanation = Explanation(edges=[ExplanationEdge(transaction_id=anchor_id, importance=.95)])
    report = ReportInput(
        run_id=run_id, evidence_id=evidence.evidence_id, selected_transaction_id=anchor_id,
        analysis_cutoff=request.analysis_cutoff, threshold=request.threshold,
        suspicion_score=anchor.suspicion_score, evidence=evidence, model_explanation=explanation,
    )
    return Detection(
        **anchor.model_dump(), evidence_id=evidence.evidence_id,
        observed_patterns=sorted({p.kind for p in observed}), graph=graph,
        model_explanation=explanation, evidence=evidence, report_input=report,
    )


def build_results(run_id: str, request: RunRequest, all_rows, target) -> Results:
    selected = [] if request.mock_scenario == "empty" else [r for r in target if r.is_detected]
    selected.sort(key=lambda r: (-r.suspicion_score, r.transaction.transaction_id))
    items = [build_detection(run_id, r, all_rows, request) for r in selected]
    return Results(
        run_id=run_id, parameters=request, generated_at=utc_now(),
        summary=Summary(dataset_account_count=len(account_ids(all_rows)), active_account_count=len(account_ids(target)),
                        transaction_count=len(target), detected_transaction_count=len(items), totals_by_currency=totals(target)),
        total=len(items), offset=0, limit=max(len(items), 1), has_more=False, items=items,
    )
