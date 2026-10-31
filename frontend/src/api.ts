import type {
  AuthCheckResponse,
  AutoAnalyzeResponse,
  DatasetAliasesResponse,
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

const PASSWORD_STORAGE_KEY = 'nhmfl-api-password'

// The hosted backend is password-protected; the local one is not.
export function getPassword(): string {
  try {
    return localStorage.getItem(PASSWORD_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setPassword(password: string): void {
  try {
    localStorage.setItem(PASSWORD_STORAGE_KEY, password)
  } catch {
    // storage unavailable (private window); the password lasts this page only
  }
  sessionPassword = password
}

let sessionPassword = getPassword()

// The hosted backend may answer each request from a different instance, so
// every request names the loaded dataset instead of relying on server state.
let currentDataset = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-App-Password': sessionPassword,
        ...(currentDataset ? { 'X-Dataset': currentDataset } : {}),
      },
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
  // The hosted backend sends plots inline as data: URLs.
  if (url.startsWith('data:')) return url
  // <img> requests can't send headers, so the password rides in the URL.
  const key = sessionPassword ? `?key=${encodeURIComponent(sessionPassword)}` : ''
  return `${API_BASE_URL}${url}${key}`
}

export const api = {
  authCheck: () => request<AuthCheckResponse>('/api/auth/check'),

  defaultPath: () => request<DefaultPathResponse>('/api/dataset/default-path'),

  datasetAliases: () => request<DatasetAliasesResponse>('/api/dataset/aliases'),

  loadDataset: async (path?: string) => {
    const response = await request<LoadDatasetResponse>('/api/dataset/load', {
      method: 'POST',
      body: JSON.stringify({ path: path || null }),
    })
    currentDataset = response.dataset ?? path ?? ''
    return response
  },

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

  exportSearch: (params?: SearchRequest) =>
    request<ExportResponse>('/api/search/export', {
      method: 'POST',
      body: params ? JSON.stringify(params) : undefined,
    }),
}

// Saves an export in the browser when the backend sends its contents, and
// returns a status message for the panel.
export function saveExport(response: ExportResponse): string {
  if (response.content === undefined) return `Exported to ${response.path}`
  const filename = response.filename ?? 'export.csv'
  const url = URL.createObjectURL(new Blob([response.content], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
  return `Downloaded ${filename}`
}
