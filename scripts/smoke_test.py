"""표준 라이브러리만 사용하는 /detect 1회 호출 검증."""
import argparse
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    headers = {"Content-Type": "application/json"}
    if os.getenv("API_KEY"):
        headers["X-API-Key"] = os.environ["API_KEY"]
    body = {"tx_ids": ["TX_99198", "TX_99199", "TX_99200", "TX_99201"], "threshold": 0.8}
    request = Request(args.base_url.rstrip("/") + "/api/v1/detect", data=json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8')}") from exc
    if result.get("is_mock") is not True:
        raise SystemExit("이 검증은 GNN Mock 전용입니다. is_mock=true를 확인하세요.")
    predictions = result["predictions"]
    if [item["tx_id"] for item in predictions] != body["tx_ids"]:
        raise SystemExit("응답 순서 또는 개수가 요청과 다릅니다")
    if [item["anomaly_score"] for item in predictions] != [0.42, 0.63, 0.58, 0.94]:
        raise SystemExit("골든 케이스 점수가 예상과 다릅니다")
    if [item["is_detected"] for item in predictions] != [False, False, False, True]:
        raise SystemExit("임계값 판정이 예상과 다릅니다")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("OK: 4 predictions, 1 detected transaction")


if __name__ == "__main__":
    main()
