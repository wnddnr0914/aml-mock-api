"""공유용 규격/예시를 서버 없이 생성한다."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import app
from models import RunRequest
from pipeline import build_results, score_transactions


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)
    request = RunRequest()
    result = build_results("00000000-0000-4000-8000-000000000001", request, *score_transactions(request))
    result.items = result.items[:1]
    result.limit, result.has_more, result.next_offset = 1, True, 1
    write(ROOT / "openapi.json", app.openapi())
    write(examples / "request.json", request.model_dump(mode="json"))
    write(examples / "results.json", result.model_dump(mode="json"))
    print("Generated openapi.json, examples/request.json, examples/results.json")
