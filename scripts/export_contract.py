"""API 계약과 예시 생성. 서버 실행·외부 호출 없이 동작합니다."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import DetectRequest, DetectResponse, MockPredictor, Prediction, app


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    request = DetectRequest(tx_ids=["TX_99198", "TX_99199", "TX_99200", "TX_99201"])
    predictor = MockPredictor(ROOT / "golden_case.json")
    response = DetectResponse(
        is_mock=predictor.is_mock, model_version=predictor.model_version, threshold=request.threshold,
        predictions=[Prediction(tx_id=tx_id, anomaly_score=score, is_detected=score >= request.threshold)
                     for tx_id, score in zip(request.tx_ids, predictor.predict(request.tx_ids), strict=True)],
    )
    (ROOT / "examples").mkdir(exist_ok=True)
    write(ROOT / "openapi.json", app.openapi())
    write(ROOT / "examples" / "request.json", request.model_dump(mode="json"))
    write(ROOT / "examples" / "response.json", response.model_dump(mode="json"))
    print("Generated openapi.json and request/response examples")
