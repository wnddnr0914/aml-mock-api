// 브라우저 또는 TypeScript 프로젝트에서 사용. UI 프레임워크 의존성 없음.
type RunStatus = {
  run_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  status_url: string;
  results_url: string;
  error: null | { code: string; message: string; retryable: boolean };
};

// 중첩 필드는 openapi.json 또는 examples/results.json 기준으로 타입을 확장한다.
type ResultsPage = {
  run_id: string;
  total: number;
  next_offset: number | null;
  has_more: boolean;
  items: Array<{
    transaction: { transaction_id: string; amount: string; currency: string };
    suspicion_score: number;
    graph: unknown;
    report_input: unknown;
  }>;
};

export function createMockClient(baseUrl: string, apiKey = "") {
  const base = baseUrl.replace(/\/$/, "");

  async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (apiKey) headers.set("X-API-Key", apiKey);
    if (init.body) headers.set("Content-Type", "application/json");
    const response = await fetch(base + path, { ...init, headers });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(`${response.status} ${data.error?.code ?? "HTTP_ERROR"}: ${data.error?.message ?? response.statusText}`);
    }
    return data as T;
  }

  return {
    async analyze(options: {
      start_date: string;
      end_date: string;
      threshold?: number;
      mock_scenario?: "success" | "empty" | "failure";
    }, onProgress: (status: RunStatus) => void, signal?: AbortSignal) {
      const headers = { "Idempotency-Key": crypto.randomUUID() };
      let run = await call<RunStatus>("/api/v1/runs", {
        method: "POST", headers, body: JSON.stringify(options), signal,
      });
      const deadline = Date.now() + 120_000;
      onProgress(run);
      while (run.status === "queued" || run.status === "running") {
        signal?.throwIfAborted();
        if (Date.now() >= deadline) throw new Error(`대기 시간 초과: ${run.run_id}`);
        await new Promise<void>((resolve) => setTimeout(resolve, 1000));
        signal?.throwIfAborted();
        run = await call<RunStatus>(run.status_url, { signal });
        onProgress(run);
      }
      if (run.status === "failed") throw new Error(run.error?.message ?? "분석 실패");
      const page = await call<ResultsPage>(`${run.results_url}?offset=0&limit=20`, { signal });
      return { run, page };
    },
    results(runId: string, offset = 0, limit = 20, signal?: AbortSignal) {
      return call<ResultsPage>(`/api/v1/runs/${encodeURIComponent(runId)}/results?offset=${offset}&limit=${limit}`, { signal });
    },
  };
}

// const client = createMockClient("http://localhost:8000", "개발 키 또는 빈 문자열");
// const controller = new AbortController();
// const { run, page } = await client.analyze(
//   { start_date: "2026-10-01", end_date: "2026-10-03" },
//   (status) => console.log(status.stage, status.progress), controller.signal,
// );
// 화면 이동 시 controller.abort(); page.items[i].report_input을 보고서 모듈에 전달.
