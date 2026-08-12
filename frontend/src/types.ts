// Types mirroring the FastAPI response/request shapes in ../api.py

export interface LoadDatasetResponse {
  count: number
  skipped: number
  filenames: string[]
}

export interface ExperimentsResponse {
  filenames: string[]
}

export interface StandardPlotColumns {
  magnetic_field: string | null
  timestamp: string | null
  temperature: string | null
  angle: string | null
  counter: string | null
  primary_measurement: string | null
}

export interface AutoAnalyzeStructure {
  independent_variable: string | null
  category: string | null
  constant_parameters: string[]
  measurements: string[]
}

export interface ExperimentGuide {
  standard_plot_columns: StandardPlotColumns
  auto_analyze_structure: AutoAnalyzeStructure
  preview_columns: string[]
  preview_rows: Record<string, unknown>[]
}

export interface PlotEntry {
  title: string
  url: string | null
}

export interface StandardPlotsResponse {
  plots: PlotEntry[]
}

export interface ConstantParameter {
  parameter: string
  average: number | null
  min: number | null
  max: number | null
  unit: string
}

export interface AutoAnalyzePlot {
  measurement: string
  independent_variable: string
  url: string
}

export interface AutoAnalyzeResponse {
  x_label: string | null
  constant_parameters: ConstantParameter[]
  measurements: string[]
  plots: AutoAnalyzePlot[]
}

export interface RangeStatistics {
  min: number | null
  max: number | null
  mean: number | null
}

export interface SearchResultSummary {
  filename: string
  score: number
  reason: string
  signal: string
  temperature_range: [number, number] | null
  field_range: [number, number] | null
  signal_to_noise_ratio: number | null
  peak_count: number | null
}

export interface PeakCountEntry {
  filename: string
  peak_count: number
}

export interface SummaryResponse {
  total_experiments: number
  skipped_files: number
  temperature: RangeStatistics
  magnetic_field: RangeStatistics
  detected_oscillation_count: number
  highest_snr: SearchResultSummary[]
  largest_peak_counts: PeakCountEntry[]
}

export interface SearchRequest {
  field_min?: number
  field_max?: number
  temperature_min?: number
  temperature_max?: number
  oscillations: boolean
  peaks_min?: number
  snr: boolean
  top: number
}

export interface SearchResponse {
  results: SearchResultSummary[]
}

export interface ExportResponse {
  path: string
}

export interface DefaultPathResponse {
  path: string
}

export interface ApiErrorBody {
  detail: string
}
