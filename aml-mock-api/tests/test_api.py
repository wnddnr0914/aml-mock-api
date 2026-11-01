"""stdlib만 사용하는 실제 HTTP 통합 검증: python -m unittest discover -s tests -v."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]


class Server:
    def __init__(self, delay="0.03"):
        # 일부 Windows sandbox의 시스템 TEMP는 생성 후 쓰기가 제한된다.
        self.temp = tempfile.TemporaryDirectory(prefix="aml-mock-http-", dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.delay = delay
        self.process = None
        self.log = None
        self.opener = build_opener(ProxyHandler({}))

    def start(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, DATA_DIR=str(self.directory / "data"), API_KEY="test-key",
                   MOCK_STAGE_DELAY_SECONDS=self.delay,
                   CORS_ORIGINS="http://localhost:5173")
        self.log = (self.directory / "server.log").open("ab")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
             "--port", str(port), "--workers", "1", "--log-level", "info"],
            cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 20
        last_error = None
        while time.monotonic() < deadline:
            try:
                last_response = self.request("GET", "/healthz", authenticated=False)
                if last_response[0] == 200:
                    return self
                last_error = repr(last_response)
            except (URLError, TimeoutError, ConnectionError) as exc:
                last_error = repr(exc)
            if self.process.poll() is not None:
                break
            time.sleep(0.03)
        self.stop()
        output = (self.directory / "server.log").read_text(encoding="utf-8", errors="replace")
        self.temp.cleanup()
        raise RuntimeError(f"localhost startup failed: {last_error}\n{output}")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log is not None:
            self.log.close()
            self.log = None

    def close(self):
        self.stop()
        self.temp.cleanup()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()

    def request(self, method, path, body=None, *, authenticated=True, headers=None):
        request_headers = {"X-API-Key": "test-key"} if authenticated else {}
        if headers:
            request_headers.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(self.base + path, data=data, headers=request_headers, method=method)
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            content = json.loads(raw) if "application/json" in response.headers.get("Content-Type", "") else raw.decode()
            return response.status, content, response.headers

    def submit(self, body=None, headers=None):
        code, result, response_headers = self.request("POST", "/api/v1/runs", body or {}, headers=headers)
        if code != 202:
            raise AssertionError((code, result))
        return result, response_headers

    def wait(self, run_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            code, status, _ = self.request("GET", f"/api/v1/runs/{run_id}")
            if code != 200:
                raise AssertionError((code, status))
            if status["status"] in {"succeeded", "failed"}:
                return status
            time.sleep(0.02)
        raise AssertionError("분석이 제한 시간 안에 종료되지 않았습니다")

    def complete(self, body=None):
        run, _ = self.submit(body)
        status = self.wait(run["run_id"])
        if status["status"] != "succeeded":
            raise AssertionError(status)
        code, result, _ = self.request("GET", run["results_url"])
        if code != 200:
            raise AssertionError((code, result))
        return status, result


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_health_and_exactly_three_documented_endpoints(self):
        code, health, _ = self.server.request("GET", "/healthz", authenticated=False)
        self.assertEqual((code, health["status"]), (200, "ok"))
        code, schema, _ = self.server.request("GET", "/openapi.json", authenticated=False)
        self.assertEqual(code, 200)
        self.assertEqual(set(schema["paths"]), {
            "/api/v1/runs", "/api/v1/runs/{run_id}", "/api/v1/runs/{run_id}/results"})
        self.assertEqual(self.server.request("GET", "/docs", authenticated=False)[0], 200)

    def test_authentication_and_unknown_run(self):
        for path, method, body in [("/api/v1/runs", "POST", {}),
                                   ("/api/v1/runs/missing", "GET", None),
                                   ("/api/v1/runs/missing/results", "GET", None)]:
            for headers in ({}, {"X-API-Key": "wrong-key"}):
                with self.subTest(path=path, headers=headers):
                    code, error, _ = self.server.request(method, path, body, authenticated=False, headers=headers)
                    self.assertEqual((code, error["error"]["code"]), (401, "UNAUTHORIZED"))
        code, error, _ = self.server.request("GET", "/api/v1/runs/missing")
        self.assertEqual((code, error["error"]["code"]), (404, "RUN_NOT_FOUND"))

    def test_success_lifecycle_and_versions(self):
        run, headers = self.server.submit()
        self.assertEqual((run["status"], run["progress"]), ("queued", 0))
        self.assertEqual(headers["Location"], run["status_url"])
        self.assertEqual(headers["Retry-After"], "1")
        status = self.server.wait(run["run_id"])
        self.assertEqual((status["status"], status["stage"], status["progress"]), ("succeeded", "completed", 100))
        self.assertIsNotNone(status["started_at"])
        self.assertIsNotNone(status["finished_at"])
        self.assertLessEqual(status["created_at"], status["started_at"])
        self.assertLessEqual(status["started_at"], status["finished_at"])
        code, result, _ = self.server.request("GET", run["results_url"])
        self.assertEqual(code, 200)
        self.assertEqual(result["run_id"], run["run_id"])
        self.assertEqual(result["versions"], status["versions"])
        self.assertTrue(result["versions"]["is_mock"])
        self.assertEqual(result["dataset_timezone"], "UTC")
        self.assertEqual(result["summary"]["transaction_count"], 24)
        self.assertEqual(result["total"], 12)

    def test_pending_results_are_409(self):
        with Server(delay="0.5") as server:
            run, _ = server.submit()
            code, error, _ = server.request("GET", run["results_url"])
            self.assertEqual((code, error["error"]["code"]), (409, "RESULTS_NOT_READY"))
            self.assertIn(error["status"], {"queued", "running"})
            self.assertTrue(error["error"]["retryable"])

    def test_empty_is_success_with_original_period_summary(self):
        status, result = self.server.complete({"mock_scenario": "empty"})
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual((result["total"], result["items"], result["has_more"]), (0, [], False))
        self.assertEqual(result["summary"]["transaction_count"], 24)
        self.assertEqual(result["summary"]["detected_transaction_count"], 0)

    def test_failure_has_status_error_and_no_result(self):
        run, _ = self.server.submit({"mock_scenario": "failure"})
        status = self.server.wait(run["run_id"])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error"]["code"], "MOCK_PIPELINE_FAILED")
        self.assertLess(status["progress"], 100)
        code, error, _ = self.server.request("GET", run["results_url"])
        self.assertEqual((code, error["error"]["code"], error["status"]), (409, "RUN_FAILED", "failed"))

    def test_invalid_inputs_are_structured_422(self):
        invalid = [
            {"start_date": "2026-09-30"}, {"end_date": "2026-10-04"},
            {"start_date": "2026-10-03", "end_date": "2026-10-01"},
            {"threshold": 1.1}, {"threshold": -0.1}, {"unknown": True},
            {"analysis_cutoff": "2026-10-01T09:00:00"},
            {"analysis_cutoff": "2026-10-01T00:00:00Z"},
            {"analysis_cutoff": "2026-10-04T00:00:01Z"},
            {"max_graph_nodes": 1}, {"max_graph_edges": 0},
            {"mock_scenario": "unknown"},
        ]
        for body in invalid:
            with self.subTest(body=body):
                code, error, _ = self.server.request("POST", "/api/v1/runs", body)
                self.assertEqual((code, error["error"]["code"]), (422, "VALIDATION_ERROR"))
                self.assertTrue(error["details"])
        for query in ("limit=101", "limit=0", "offset=-1"):
            self.assertEqual(self.server.request("GET", f"/api/v1/runs/missing/results?{query}")[0], 422)

    def test_cutoff_is_exclusive_for_targets_and_evidence(self):
        _, result = self.server.complete({"start_date": "2026-10-01", "end_date": "2026-10-01",
                                          "analysis_cutoff": "2026-10-01T09:05:00Z"})
        self.assertEqual(result["summary"]["transaction_count"], 1)
        self.assertEqual([x["transaction"]["transaction_id"] for x in result["items"]], ["tx-01-001"])
        self.assertEqual([x["transaction_id"] for x in result["items"][0]["evidence"]["transactions"]], ["tx-01-001"])

    def test_threshold_is_inclusive(self):
        _, exact = self.server.complete({"threshold": 0.93})
        self.assertEqual(exact["total"], 3)
        self.assertTrue(all(item["suspicion_score"] == 0.93 for item in exact["items"]))
        _, above = self.server.complete({"threshold": 0.930001})
        self.assertEqual(above["total"], 0)

    def test_currency_totals_and_repeated_transactions_are_preserved(self):
        _, result = self.server.complete()
        totals = {x["currency"]: (Decimal(x["amount"]), x["transaction_count"])
                  for x in result["summary"]["totals_by_currency"]}
        self.assertEqual(totals, {"EUR": (Decimal("13140.90"), 9), "USD": (Decimal("17100.93"), 15)})
        item = result["items"][0]
        transactions = item["evidence"]["transactions"]
        self.assertEqual(len(transactions), 21)
        self.assertEqual(len({x["transaction_id"] for x in transactions}), 21)
        pair = [x for x in transactions if x["source"]["account_number"] == "A"
                and x["target"]["account_number"] == "HUB"]
        self.assertEqual(len(pair), 6)
        self.assertEqual({x["amount"] for x in pair}, {"1000.10", "100.01"})
        self.assertTrue(any(not edge["is_detected"] for edge in item["graph"]["edges"]))

    def test_display_limits_preserve_anchor_and_full_report_evidence(self):
        _, result = self.server.complete({"max_graph_nodes": 2, "max_graph_edges": 1})
        for item in result["items"]:
            graph, evidence, report = item["graph"], item["evidence"], item["report_input"]
            anchor = item["transaction"]["transaction_id"]
            self.assertEqual((len(graph["nodes"]), len(graph["edges"])), (2, 1))
            self.assertTrue(graph["truncated"])
            self.assertEqual(graph["edges"][0]["transaction"]["transaction_id"], anchor)
            self.assertTrue(graph["edges"][0]["is_selected"])
            self.assertEqual(graph["omitted_edges"] + len(graph["edges"]), graph["total_edges"])
            self.assertEqual(len(evidence["transactions"]), 21)
            self.assertEqual(report["evidence"], evidence)
            self.assertEqual(report["evidence_id"], item["evidence_id"])
            self.assertEqual(report["run_id"], result["run_id"])
            self.assertTrue(report["missing_information"])
            self.assertEqual(item["model_explanation"]["method"], "mock_fixture")
            self.assertTrue(item["model_explanation"]["is_mock"])

    def test_history_scope_does_not_expand_target_period(self):
        body = {"start_date": "2026-10-02", "end_date": "2026-10-02", "history_days": 1}
        _, with_history = self.server.complete(body)
        _, without_history = self.server.complete(dict(body, history_days=0))
        self.assertEqual(with_history["summary"]["transaction_count"], 8)
        self.assertEqual(with_history["total"], 4)
        self.assertTrue(all(x["transaction"]["transaction_id"].startswith("tx-02-") for x in with_history["items"]))
        self.assertEqual(len(with_history["items"][0]["evidence"]["transactions"]), 14)
        self.assertTrue(with_history["items"][0]["evidence"]["history_included"])
        self.assertEqual(len(without_history["items"][0]["evidence"]["transactions"]), 7)
        self.assertFalse(without_history["items"][0]["evidence"]["history_included"])

    def test_pagination_is_stable_and_summary_is_global(self):
        status, complete = self.server.complete()
        all_ids = []
        for offset in range(0, complete["total"], 2):
            code, page, _ = self.server.request("GET", status["results_url"] + f"?offset={offset}&limit=2")
            self.assertEqual(code, 200)
            self.assertEqual(page["summary"], complete["summary"])
            self.assertEqual(page["total"], complete["total"])
            self.assertEqual(page["has_more"], offset + 2 < complete["total"])
            self.assertEqual(page["next_offset"], offset + 2 if page["has_more"] else None)
            all_ids.extend(x["transaction"]["transaction_id"] for x in page["items"])
        self.assertEqual(all_ids, [x["transaction"]["transaction_id"] for x in complete["items"]])
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(complete["items"], sorted(complete["items"], key=lambda x: (-x["suspicion_score"], x["transaction"]["transaction_id"])))
        _, beyond, _ = self.server.request("GET", status["results_url"] + "?offset=999")
        self.assertEqual((beyond["items"], beyond["has_more"], beyond["total"]), ([], False, complete["total"]))

    def test_idempotency_replays_normalized_request_and_rejects_conflict(self):
        headers = {"Idempotency-Key": "retry-same-analysis"}
        original, _ = self.server.submit(headers=headers)
        replay, _ = self.server.submit({"threshold": 0.8}, headers=headers)
        self.assertEqual(original["run_id"], replay["run_id"])
        code, error, _ = self.server.request("POST", "/api/v1/runs", {"threshold": 0.9}, headers=headers)
        self.assertEqual((code, error["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))
        other, _ = self.server.submit()
        self.assertNotEqual(original["run_id"], other["run_id"])
        self.server.wait(original["run_id"])
        self.server.wait(other["run_id"])
        for run in (original, other):
            _, result, _ = self.server.request("GET", run["results_url"])
            self.assertTrue(all(x["report_input"]["run_id"] == run["run_id"] for x in result["items"]))

    def test_cors_allows_configured_frontend_and_headers(self):
        code, _, headers = self.server.request("OPTIONS", "/api/v1/runs", authenticated=False, headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key,idempotency-key"})
        self.assertEqual(code, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        _, _, denied = self.server.request("GET", "/healthz", headers={"Origin": "https://unlisted.example"})
        self.assertIsNone(denied.get("Access-Control-Allow-Origin"))
        _, _, allowed = self.server.request("GET", "/healthz", headers={"Origin": "http://localhost:5173"})
        self.assertIn("Location", allowed["Access-Control-Expose-Headers"])

    def test_restart_preserves_results_and_fails_interrupted_work(self):
        with Server(delay="0.2") as server:
            completed, _ = server.submit(headers={"Idempotency-Key": "persistent-completed"})
            self.assertEqual(server.wait(completed["run_id"])["status"], "succeeded")
            _, saved, _ = server.request("GET", completed["results_url"])
            interrupted, _ = server.submit(headers={"Idempotency-Key": "persistent-interrupted"})
            server.stop()
            server.start()
            _, restored, _ = server.request("GET", completed["results_url"])
            self.assertEqual(restored, saved)
            failed = server.wait(interrupted["run_id"])
            self.assertEqual((failed["status"], failed["error"]["code"]), ("failed", "SERVER_RESTARTED"))
            replay, _ = server.submit(headers={"Idempotency-Key": "persistent-completed"})
            self.assertEqual(replay["run_id"], completed["run_id"])
            code, error, _ = server.request("GET", interrupted["results_url"])
            self.assertEqual((code, error["error"]["code"]), (409, "RUN_FAILED"))


if __name__ == "__main__":
    unittest.main()
