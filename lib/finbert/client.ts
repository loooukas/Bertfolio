import type { AnalysisResponseBackend, BackendJobPayload } from "@/lib/finbert/types"
import type { AnalyzeRunOverrides } from "@/lib/finbert/ui-settings"

class FinbertClientError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "FinbertClientError"
    this.status = status
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T
  }

  let message = `Request failed (${response.status})`
  try {
    const payload = (await response.json()) as { detail?: string; error?: string }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      message = payload.detail
    } else if (typeof payload.error === "string" && payload.error.trim()) {
      message = payload.error
    }
  } catch {
    // Ignore non-JSON error payloads.
  }

  throw new FinbertClientError(message, response.status)
}

export async function createAnalyzeJob(ticker: string, runtimeOverrides?: AnalyzeRunOverrides): Promise<BackendJobPayload> {
  const response = await fetch("/api/analyze/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker,
      runtime_overrides: runtimeOverrides || undefined,
    }),
  })
  return parseResponse<BackendJobPayload>(response)
}

export async function getAnalyzeJob(jobId: string): Promise<BackendJobPayload> {
  const response = await fetch(`/api/analyze/jobs/${encodeURIComponent(jobId)}`)
  return parseResponse<BackendJobPayload>(response)
}

export async function getAnalyzeResult(jobId: string): Promise<BackendJobPayload> {
  const response = await fetch(`/api/analyze/jobs/${encodeURIComponent(jobId)}/result`)
  return parseResponse<BackendJobPayload>(response)
}

export async function getAnalyzeReport(ticker: string): Promise<AnalysisResponseBackend> {
  const params = new URLSearchParams({ ticker })
  const response = await fetch(`/api/analyze?${params.toString()}`)
  return parseResponse<AnalysisResponseBackend>(response)
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  const response = await fetch("/api/health")
  return parseResponse<{ status: string }>(response)
}

export { FinbertClientError }
