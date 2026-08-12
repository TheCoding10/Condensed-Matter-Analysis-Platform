import type {
  AutoAnalyzeResponse,
  DefaultPathResponse,
  ExperimentGuide,
  ExperimentsResponse,
  ExportResponse,
  LoadDatasetResponse,
  SearchRequest,
  SearchResponse,
  StandardPlotsResponse,
  SummaryResponse,
} from './types'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, `Could not reach the API at ${API_BASE_URL}. Is the backend running?`)
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(response.status, detail)
  }

  return response.json() as Promise<T>
}

export function toPlotUrl(url: string | null): string | null {
  if (!url) return null
  return `${API_BASE_URL}${url}`
}

export const api = {
  defaultPath: () => request<DefaultPathResponse>('/api/dataset/default-path'),

  loadDataset: (path?: string) =>
    request<LoadDatasetResponse>('/api/dataset/load', {
      method: 'POST',
      body: JSON.stringify({ path: path || null }),
    }),

  listExperiments: () => request<ExperimentsResponse>('/api/experiments'),

  experimentGuide: (filename: string) =>
    request<ExperimentGuide>(`/api/experiments/${encodeURIComponent(filename)}/guide`),

  standardPlots: (filename: string) =>
    request<StandardPlotsResponse>(
      `/api/experiments/${encodeURIComponent(filename)}/standard-plots`,
    ),

  autoAnalyze: (filename: string) =>
    request<AutoAnalyzeResponse>(
      `/api/experiments/${encodeURIComponent(filename)}/auto-analyze`,
    ),

  summary: () => request<SummaryResponse>('/api/summary'),

  exportSummary: () => request<ExportResponse>('/api/summary/export', { method: 'POST' }),

  search: (params: SearchRequest) =>
    request<SearchResponse>('/api/search', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  exportSearch: () => request<ExportResponse>('/api/search/export', { method: 'POST' }),
}
