import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { SummaryResponse } from '../types'
import { formatNumber, formatRange } from '../lib/format'
import { Button, Card, EmptyState, ErrorBanner, SectionTitle, Spinner, StatCard, Table } from './common'

export function SummaryPanel({ datasetLoaded }: { datasetLoaded: boolean }) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!datasetLoaded) {
      setSummary(null)
      return
    }
    setLoading(true)
    setError(null)
    api
      .summary()
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load summary.'))
      .finally(() => setLoading(false))
  }, [datasetLoaded])

  async function handleExport() {
    setExportMessage(null)
    try {
      const { path } = await api.exportSummary()
      setExportMessage(`Exported to ${path}`)
    } catch (err) {
      setExportMessage(err instanceof ApiError ? err.message : 'Export failed.')
    }
  }

  if (!datasetLoaded) {
    return <EmptyState message="Load a dataset above to see the summary." />
  }

  if (loading) return <Spinner label="Computing dataset summary…" />
  if (error) return <ErrorBanner message={error} />
  if (!summary) return null

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Experiments" value={String(summary.total_experiments)} />
        <StatCard label="Skipped files" value={String(summary.skipped_files)} />
        <StatCard label="Oscillations detected" value={String(summary.detected_oscillation_count)} />
        <StatCard
          label="Temperature range"
          value={formatRange([summary.temperature.min ?? 0, summary.temperature.max ?? 0])}
          hint={`mean ${formatNumber(summary.temperature.mean)}`}
        />
        <StatCard
          label="Field range"
          value={formatRange([summary.magnetic_field.min ?? 0, summary.magnetic_field.max ?? 0])}
          hint={`mean ${formatNumber(summary.magnetic_field.mean)}`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle>Highest signal-to-noise ratio</SectionTitle>
          <div className="mt-3">
            {summary.highest_snr.length === 0 ? (
              <EmptyState message="No SNR data available." />
            ) : (
              <Table columns={['File', 'SNR', 'Peaks']}>
                {summary.highest_snr.map((result) => (
                  <tr key={result.filename}>
                    <td className="px-3 py-2 font-mono text-xs">{result.filename}</td>
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

        <Card>
          <SectionTitle>Largest peak counts</SectionTitle>
          <div className="mt-3">
            {summary.largest_peak_counts.length === 0 ? (
              <EmptyState message="No peak data available." />
            ) : (
              <Table columns={['File', 'Peaks']}>
                {summary.largest_peak_counts.map((entry) => (
                  <tr key={entry.filename}>
                    <td className="px-3 py-2 font-mono text-xs">{entry.filename}</td>
                    <td className="px-3 py-2 tabular-nums">{entry.peak_count}</td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="secondary" onClick={handleExport}>
          Export summary CSV
        </Button>
        {exportMessage && <span className="text-sm text-slate-500 dark:text-slate-400">{exportMessage}</span>}
      </div>
    </div>
  )
}
