import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, toPlotUrl } from '../api'
import type { AutoAnalyzeResponse, ExperimentGuide, PlotEntry } from '../types'
import { formatNumber } from '../lib/format'
import { Card, EmptyState, ErrorBanner, SectionTitle, Spinner, Table } from './common'

type DetailTab = 'guide' | 'standard' | 'auto'

export function ExperimentsPanel({ filenames }: { filenames: string[] }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string | null>(filenames[0] ?? null)

  useEffect(() => {
    if (!selected && filenames.length > 0) setSelected(filenames[0])
    if (selected && !filenames.includes(selected)) setSelected(filenames[0] ?? null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filenames])

  const filtered = useMemo(
    () => filenames.filter((name) => name.toLowerCase().includes(query.toLowerCase())),
    [filenames, query],
  )

  if (filenames.length === 0) {
    return <EmptyState message="No experiments in this dataset." />
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      <Card className="flex flex-col gap-3 lg:max-h-[70vh]">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter experiments…"
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
        />
        <ul className="flex flex-col gap-1 overflow-y-auto">
          {filtered.map((name) => (
            <li key={name}>
              <button
                onClick={() => setSelected(name)}
                className={`w-full truncate rounded-lg px-2 py-1.5 text-left text-xs font-mono transition-colors ${
                  selected === name
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                }`}
                title={name}
              >
                {name}
              </button>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-2 py-4 text-center text-xs text-slate-400">No matches.</li>
          )}
        </ul>
      </Card>

      {selected ? (
        <ExperimentDetail filename={selected} />
      ) : (
        <EmptyState message="Select an experiment to view details." />
      )}
    </div>
  )
}

function ExperimentDetail({ filename }: { filename: string }) {
  const [tab, setTab] = useState<DetailTab>('guide')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="truncate font-mono text-sm text-slate-700 dark:text-slate-300">{filename}</h3>
        <div className="flex gap-1 rounded-lg border border-slate-200 p-1 dark:border-slate-800">
          {(
            [
              ['guide', 'Guide'],
              ['standard', 'Standard plots'],
              ['auto', 'Auto-analyze'],
            ] as [DetailTab, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTab(value)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                tab === value
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'guide' && <GuideView filename={filename} />}
      {tab === 'standard' && <StandardPlotsView filename={filename} />}
      {tab === 'auto' && <AutoAnalyzeView filename={filename} />}
    </div>
  )
}

function GuideView({ filename }: { filename: string }) {
  const [guide, setGuide] = useState<ExperimentGuide | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setGuide(null)
    api
      .experimentGuide(filename)
      .then(setGuide)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load guide.'))
      .finally(() => setLoading(false))
  }, [filename])

  if (loading) return <Spinner label="Loading experiment guide…" />
  if (error) return <ErrorBanner message={error} />
  if (!guide) return null

  const columnEntries = Object.entries(guide.standard_plot_columns)

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <SectionTitle>Detected columns</SectionTitle>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {columnEntries.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {key.replace(/_/g, ' ')}
              </dt>
              <dd className="font-mono text-sm">{value ?? '—'}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <SectionTitle>Auto-analyze structure</SectionTitle>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Independent variable
            </dt>
            <dd className="font-mono text-sm">{guide.auto_analyze_structure.independent_variable ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Category</dt>
            <dd className="font-mono text-sm">{guide.auto_analyze_structure.category ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Constant parameters
            </dt>
            <dd className="font-mono text-sm">
              {guide.auto_analyze_structure.constant_parameters.join(', ') || '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Measurements
            </dt>
            <dd className="font-mono text-sm">{guide.auto_analyze_structure.measurements.join(', ') || '—'}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <SectionTitle>Preview (first 20 rows)</SectionTitle>
        <div className="mt-3">
          <Table columns={guide.preview_columns}>
            {guide.preview_rows.map((row, index) => (
              // eslint-disable-next-line react/no-array-index-key
              <tr key={index}>
                {guide.preview_columns.map((column) => (
                  <td key={column} className="whitespace-nowrap px-3 py-1.5 text-xs tabular-nums">
                    {formatCell(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </Table>
        </div>
      </Card>
    </div>
  )
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return formatNumber(value, 4)
  return String(value)
}

function StandardPlotsView({ filename }: { filename: string }) {
  const [plots, setPlots] = useState<PlotEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setPlots(null)
    api
      .standardPlots(filename)
      .then((response) => setPlots(response.plots))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load plots.'))
      .finally(() => setLoading(false))
  }, [filename])

  if (loading) return <Spinner label="Generating standard plots…" />
  if (error) return <ErrorBanner message={error} />
  if (!plots) return null

  return <PlotGrid plots={plots} />
}

function AutoAnalyzeView({ filename }: { filename: string }) {
  const [analysis, setAnalysis] = useState<AutoAnalyzeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setAnalysis(null)
    api
      .autoAnalyze(filename)
      .then(setAnalysis)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Auto-analysis failed.'))
      .finally(() => setLoading(false))
  }, [filename])

  if (loading) return <Spinner label="Running auto-analysis…" />
  if (error) return <ErrorBanner message={error} />
  if (!analysis) return null

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <SectionTitle>Constant parameters</SectionTitle>
        <div className="mt-3">
          {analysis.constant_parameters.length === 0 ? (
            <EmptyState message="No constant parameters detected." />
          ) : (
            <Table columns={['Parameter', 'Average', 'Min', 'Max', 'Unit']}>
              {analysis.constant_parameters.map((param) => (
                <tr key={param.parameter}>
                  <td className="px-3 py-2 font-mono text-xs">{param.parameter}</td>
                  <td className="px-3 py-2 tabular-nums">{formatNumber(param.average)}</td>
                  <td className="px-3 py-2 tabular-nums">{formatNumber(param.min)}</td>
                  <td className="px-3 py-2 tabular-nums">{formatNumber(param.max)}</td>
                  <td className="px-3 py-2">{param.unit || '—'}</td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </Card>

      <PlotGrid
        plots={analysis.plots.map((plot) => ({
          title: `${plot.measurement} vs ${plot.independent_variable}`,
          url: plot.url,
        }))}
      />
    </div>
  )
}

function PlotGrid({ plots }: { plots: PlotEntry[] }) {
  if (plots.length === 0) return <EmptyState message="No plots available." />

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {plots.map((plot) => (
        <Card key={plot.title}>
          <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">{plot.title}</p>
          {plot.url ? (
            <img
              src={toPlotUrl(plot.url) ?? undefined}
              alt={plot.title}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-800"
            />
          ) : (
            <EmptyState message="Not available for this experiment." />
          )}
        </Card>
      ))}
    </div>
  )
}
