import type { BenchmarkReport, DatasetInfo, JobDescription, RankRequest, RankResponse } from "./types";

// In dev, Vite proxies /api to the FastAPI backend (see vite.config.ts), so an
// empty base is fine. Set VITE_API_URL to point at a different backend origin.
const BASE_URL = import.meta.env?.VITE_API_URL ?? "";

export class ApiError extends Error {
  fieldErrors: Record<string, string>;

  constructor(message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("Could not connect to the server. Check that the local API is running, then try again.");
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    let detail: unknown;
    try { detail = JSON.parse(body).detail; } catch { /* Use HTTP fallback below. */ }
    const fields: Record<string, string> = {};
    if (Array.isArray(detail)) {
      for (const issue of detail) {
        const path = (issue.loc as (string | number)[]).filter((part) => part !== "body");
        fields[path.join(".")] = issue.msg;
      }
      throw new ApiError(Object.entries(fields).map(([field, message]) => `${field}: ${message}`).join("; "), fields);
    }
    throw new ApiError(typeof detail === "string" ? detail : `${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth() {
  return request<{ status: string }>("/api/health");
}

export function fetchJd() {
  return request<JobDescription>("/api/jd");
}

export function runRanking(payload: RankRequest) {
  return request<RankResponse>("/api/rank", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export const fetchDemo = () => request<DatasetInfo>("/api/datasets/demo");
export const fetchBenchmark = () => request<BenchmarkReport>("/api/benchmarks");
export function uploadDataset(file: File) {
  const body = new FormData(); body.append("file", file);
  return request<DatasetInfo>("/api/datasets", { method: "POST", body, headers: {} });
}
