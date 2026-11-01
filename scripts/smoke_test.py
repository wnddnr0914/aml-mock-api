"""외부 라이브러리 없이 실행→상태 폴링→결과 조회. API_KEY 환경변수 사용."""
import argparse
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--scenario", choices=["success", "empty", "failure"], default="success")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if os.getenv("API_KEY"):
        headers["X-API-Key"] = os.environ["API_KEY"]

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(base + path, data=data, headers=headers), timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8')}") from exc

    run = call("/api/v1/runs", {"start_date": "2026-10-01", "end_date": "2026-10-03", "mock_scenario": args.scenario})
    print(f"run_id: {run['run_id']}")
    deadline = time.monotonic() + 120
    while run["status"] not in {"succeeded", "failed"}:
        if time.monotonic() > deadline:
            raise SystemExit("120초 대기 초과. 상태 URL을 다시 조회하세요.")
        time.sleep(1)
        run = call(run["status_url"])
        print(f"{run['status']} / {run['stage']} / {run['progress']}%")
    if run["status"] == "failed":
        print(json.dumps(run["error"], ensure_ascii=False, indent=2))
        return 0 if args.scenario == "failure" else 1
    result = call(run["results_url"] + "?offset=0&limit=1")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"total={result['total']}, first page items={len(result['items'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
