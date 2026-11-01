"""표준 라이브러리만 사용하는 GNN Mock 실제 HTTP 및 fixture 검증."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import MockPredictor

GOLDEN_IDS = ["TX_99198", "TX_99199", "TX_99200", "TX_99201"]


class Server:
    def __init__(self, api_key="test-key"):
        self.temp = tempfile.TemporaryDirectory(prefix="gnn-mock-http-", dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.api_key = api_key
        self.process = None
        self.log = None
        self.opener = build_opener(ProxyHandler({}))

    def start(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, API_KEY=self.api_key, CORS_ORIGINS="http://localhost:5173")
        self.log = (self.directory / "server.log").open("ab")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
             "--workers", "1", "--log-level", "info"],
            cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 20
        last_error = None
        while time.monotonic() < deadline:
            try:
                if self.request("GET", "/healthz", authenticated=False)[0] == 200:
                    return self
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
        request_headers = {"X-API-Key": self.api_key} if authenticated else {}
        request_headers.update(headers or {})
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

    def detect(self, tx_ids=GOLDEN_IDS, threshold=0.8):
        return self.request("POST", "/api/v1/detect", {"tx_ids": tx_ids, "threshold": threshold})


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_health_swagger_has_one_business_endpoint_and_legacy_is_absent(self):
        code, health, _ = self.server.request("GET", "/healthz", authenticated=False)
        self.assertEqual((code, health), (200, {"status": "ok", "is_mock": True}))
        code, schema, _ = self.server.request("GET", "/openapi.json", authenticated=False)
        self.assertEqual(code, 200)
        self.assertEqual(set(schema["paths"]), {"/api/v1/detect"})
        self.assertEqual(set(schema["paths"]["/api/v1/detect"]), {"post"})
        self.assertEqual(self.server.request("GET", "/docs", authenticated=False)[0], 200)
        for path in ("/api/v1/runs", "/api/v1/subgraph/TX_99201", "/api/v1/report/generate"):
            with self.subTest(path=path):
                self.assertEqual(self.server.request("POST", path, {})[0], 404)

    def test_golden_case_returns_four_scores_and_one_detection(self):
        code, result, _ = self.server.detect()
        self.assertEqual(code, 200)
        self.assertTrue(result["is_mock"])
        self.assertEqual(result["model_version"], "gnn-mock-v1")
        self.assertEqual(result["threshold"], 0.8)
        predictions = result["predictions"]
        self.assertEqual([p["tx_id"] for p in predictions], GOLDEN_IDS)
        self.assertEqual([p["anomaly_score"] for p in predictions], [0.42, 0.63, 0.58, 0.94])
        self.assertEqual([p["tx_id"] for p in predictions if p["is_detected"]], ["TX_99201"])

    def test_selected_transaction_and_default_threshold(self):
        code, result, _ = self.server.request("POST", "/api/v1/detect", {"tx_ids": ["TX_99201"]})
        self.assertEqual(code, 200)
        self.assertEqual(result["threshold"], 0.8)
        self.assertEqual(result["predictions"], [{"tx_id": "TX_99201", "anomaly_score": 0.94, "is_detected": True}])

    def test_prediction_order_follows_request(self):
        ids = ["TX_99201", "TX_99198", "TX_99200"]
        code, result, _ = self.server.detect(ids)
        self.assertEqual(code, 200)
        self.assertEqual([p["tx_id"] for p in result["predictions"]], ids)
        self.assertEqual([p["anomaly_score"] for p in result["predictions"]], [0.94, 0.42, 0.58])

    def test_threshold_changes_only_flags_and_includes_equal_score(self):
        for threshold, detected in ((0, 4), (0.94, 1), (0.95, 0), (1, 0)):
            with self.subTest(threshold=threshold):
                code, result, _ = self.server.detect(threshold=threshold)
                self.assertEqual(code, 200)
                self.assertEqual([p["anomaly_score"] for p in result["predictions"]], [0.42, 0.63, 0.58, 0.94])
                self.assertEqual(sum(p["is_detected"] for p in result["predictions"]), detected)

    def test_transaction_id_validation(self):
        invalid_bodies = [
            {}, {"tx_ids": []}, {"tx_ids": ["TX_99201", "TX_99201"]},
            {"tx_ids": [""]}, {"tx_ids": ["TX/99201"]}, {"tx_ids": ["a" * 65]},
            {"tx_ids": [1]}, {"tx_ids": "TX_99201"},
            {"tx_ids": ["TX_99201"], "start_date": "2026-10-01"},
            {"tx_ids": [f"TX_NEW_{i}" for i in range(1001)]},
        ]
        for body in invalid_bodies:
            with self.subTest(body=str(body)[:90]):
                code, result, _ = self.server.request("POST", "/api/v1/detect", body)
                self.assertEqual((code, result["error"]["code"]), (422, "VALIDATION_ERROR"))
                self.assertTrue(result["error"]["details"])
        code, _, _ = self.server.detect([f"TX_NEW_{i}" for i in range(1000)])
        self.assertEqual(code, 404)  # 1000개는 목록 길이 검증을 통과하고 ID 존재 확인으로 진행한다.

    def test_threshold_validation_is_finite_numeric_and_bounded(self):
        for threshold in (-0.001, 1.001, float("nan"), float("inf"), "0.8", True, None):
            with self.subTest(threshold=threshold):
                code, result, _ = self.server.detect(["TX_99201"], threshold=threshold)
                self.assertEqual((code, result["error"]["code"]), (422, "VALIDATION_ERROR"))

    def test_unknown_id_rejects_whole_request_without_partial_predictions(self):
        for ids in (["TX_99201", "TX_UNKNOWN"], ["TX_MISSING", "TX_99198", "TX_UNKNOWN"]):
            with self.subTest(ids=ids):
                code, result, _ = self.server.detect(ids)
                self.assertEqual((code, result["error"]["code"]), (404, "UNKNOWN_TX_ID"))
                self.assertEqual(result["error"]["unknown_tx_ids"], [tx for tx in ids if tx not in GOLDEN_IDS])
                self.assertNotIn("predictions", result)

    def test_auth_required_when_configured_and_optional_without_key(self):
        for headers in ({}, {"X-API-Key": "wrong"}):
            with self.subTest(headers=headers):
                code, result, _ = self.server.request("POST", "/api/v1/detect", {"tx_ids": ["TX_99201"]}, authenticated=False, headers=headers)
                self.assertEqual((code, result["error"]["code"]), (401, "UNAUTHORIZED"))
        with Server(api_key="") as local:
            code, result, _ = local.request("POST", "/api/v1/detect", {"tx_ids": ["TX_99201"]}, authenticated=False)
            self.assertEqual(code, 200)
            self.assertEqual(result["predictions"][0]["anomaly_score"], 0.94)

    def test_cors_allows_configured_frontend_and_api_key_header(self):
        code, _, headers = self.server.request("OPTIONS", "/api/v1/detect", authenticated=False, headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key"})
        self.assertEqual(code, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        code, _, headers = self.server.request("POST", "/api/v1/detect", {"tx_ids": ["TX_99201"]}, headers={"Origin": "https://unlisted.example"})
        self.assertEqual(code, 200)
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

    def test_response_contains_only_inference_contract(self):
        code, result, _ = self.server.detect()
        self.assertEqual(code, 200)
        self.assertEqual(set(result), {"is_mock", "model_version", "threshold", "predictions"})
        for item in result["predictions"]:
            self.assertEqual(set(item), {"tx_id", "anomaly_score", "is_detected"})
        for forbidden in ("graph", "evidence", "report_input", "model_explanation", "run_id", "stage"):
            self.assertNotIn(forbidden, json.dumps(result))


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gnn-mock-fixture-", dir=ROOT / "tests")
        self.path = Path(self.temp.name) / "fixture.json"
        self.original = json.loads((ROOT / "golden_case.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def assert_invalid(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises((ValueError, KeyError, TypeError)):
            MockPredictor(self.path)

    def test_fixture_rejects_out_of_range_or_non_finite_scores(self):
        for value in (-0.01, 1.01, float("nan"), "0.94"):
            with self.subTest(value=value):
                data = copy.deepcopy(self.original)
                data["mock_model"]["scores"]["TX_99201"] = value
                self.assert_invalid(data)

    def test_fixture_requires_unique_matching_ids_and_model_version(self):
        for mutation in ("missing_score", "extra_score", "duplicate_id", "empty_transactions", "empty_version"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(self.original)
                if mutation == "missing_score":
                    del data["mock_model"]["scores"]["TX_99201"]
                elif mutation == "extra_score":
                    data["mock_model"]["scores"]["TX_UNKNOWN"] = 0.5
                elif mutation == "duplicate_id":
                    data["transactions"].append(copy.deepcopy(data["transactions"][0]))
                elif mutation == "empty_transactions":
                    data["transactions"] = []
                else:
                    data["mock_model"]["model_version"] = " "
                self.assert_invalid(data)


if __name__ == "__main__":
    unittest.main()
