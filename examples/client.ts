export type Prediction = { tx_id: string; anomaly_score: number; is_detected: boolean };
export type DetectResponse = {
  is_mock: boolean;
  model_version: string;
  threshold: number;
  predictions: Prediction[];
};

// 사용자 브라우저에 넣는 키는 팀 개발용 공통 키입니다.
export async function detect(
  baseUrl: string,
  apiKey: string,
  txIds: string[],
  threshold = 0.8,
  signal?: AbortSignal,
): Promise<DetectResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/v1/detect`, {
    method: "POST", headers, body: JSON.stringify({ tx_ids: txIds, threshold }), signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(`${response.status} ${result.error?.code ?? "HTTP_ERROR"}: ${result.error?.message ?? response.statusText}`);
  return result as DetectResponse;
}

// const data = await detect("https://서비스주소.onrender.com", "팀 개발 키", ["TX_99201"]);
// data.predictions를 tx_id로 원본 거래에 연결해 표시합니다.
