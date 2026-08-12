import { useState } from 'react'
import { api, ApiError } from '../api'
import type { SearchRequest, SearchResultSummary } from '../types'
import { formatNumber, formatRange } from '../lib/format'
import { Button, Card, EmptyState, ErrorBanner, SectionTitle, Spinner, Table } from './common'

const emptyForm = {
  fieldMin: '',
  fieldMax: '',
  temperatureMin: '',
  temperatureMax: '',
  oscillations: false,
  peaksMin: '',
  snr: false,
  top: '10',
}

type FormState = typeof emptyForm

export function SearchPanel({ datasetLoaded }: { datasetLoaded: boolean }) {
  const [form, setForm] = useState<FormState>(emptyForm)
  const [results, setResults] = useState<SearchResultSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function toNumber(value: string): number | undefined {
    if (value.trim() === '') return undefined
    const parsed = Number(value)
    return Number.isNaN(parsed) ? undefined : parsed
  }

  async function runSearch(event: React.FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setExportMessage(null)

    const request: SearchRequest = {
      field_min: toNumber(form.fieldMin),
      field_max: toNumber(form.fieldMax),
      temperature_min: toNumber(form.temperatureMin),
      temperature_max: toNumber(form.temperatureMax),
      oscillations: form.oscillations,
      peaks_min: toNumber(form.peaksMin),
      snr: form.snr,
      top: toNumber(form.top) ?? 10,
    }

    try {
      const response = await api.search(request)
      setResults(response.results)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Search failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleExport() {
    setExportMessage(null)
    try {
      const { path } = await api.exportSearch()
      setExportMessage(`Exported to ${path}`)
    } catch (err) {
      setExportMessage(err instanceof ApiError ? err.message : 'Export failed.')
    }
  }

  if (!datasetLoaded) {
    return <EmptyState message="Load a dataset above to search experiments." />
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <form onSubmit={runSearch} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Field min (T)">
              <NumberInput value={form.fieldMin} onChange={(v) => update('fieldMin', v)} />
            </Field>
            <Field label="Field max (T)">
              <NumberInput value={form.fieldMax} onChange={(v) => update('fieldMax', v)} />
            </Field>
            <Field label="Temp min (K)">
              <NumberInput value={form.temperatureMin} onChange={(v) => update('temperatureMin', v)} />
            </Field>
            <Field label="Temp max (K)">
              <NumberInput value={form.temperatureMax} onChange={(v) => update('temperatureMax', v)} />
            </Field>
            <Field label="Min peak count">
              <NumberInput value={form.peaksMin} onChange={(v) => update('peaksMin', v)} />
            </Field>
            <Field label="Top N results">
              <NumberInput value={form.top} onChange={(v) => update('top', v)} />
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <Checkbox
              label="Contains oscillations"
              checked={form.oscillations}
              onChange={(v) => update('oscillations', v)}
            />
            <Checkbox
              label="Rank by signal-to-noise ratio"
              checked={form.snr}
              onChange={(v) => update('snr', v)}
            />
          </div>
          <div>
            <Button type="submit" disabled={loading}>
              {loading ? 'Searching…' : 'Search'}
            </Button>
          </div>
        </form>
      </Card>

      {error && <ErrorBanner message={error} />}
      {loading && <Spinner label="Searching experiments…" />}

      {results && !loading && (
        <Card>
          <div className="flex items-center justify-between">
            <SectionTitle>Results ({results.length})</SectionTitle>
            {results.length > 0 && (
              <Button variant="secondary" onClick={handleExport}>
                Export CSV
              </Button>
            )}
          </div>
          {exportMessage && (
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{exportMessage}</p>
          )}
          <div className="mt-3">
            {results.length === 0 ? (
              <EmptyState message="No experiments matched the selected criteria." />
            ) : (
              <Table columns={['File', 'Score', 'Reason', 'Temp range', 'Field range', 'SNR', 'Peaks']}>
                {results.map((result) => (
                  <tr key={result.filename}>
                    <td className="px-3 py-2 font-mono text-xs">{result.filename}</td>
                    <td className="px-3 py-2 tabular-nums">{formatNumber(result.score)}</td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {result.reason}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{formatRange(result.temperature_range)}</td>
                    <td className="px-3 py-2 tabular-nums">{formatRange(result.field_range)}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {formatNumber(result.signal_to_noise_ratio)}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{result.peak_count ?? '—'}</td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
      {children}
    </label>
  )
}

function NumberInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input
      type="number"
      step="any"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
    />
  )
}

function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600"
      />
      {label}
    </label>
  )
}
