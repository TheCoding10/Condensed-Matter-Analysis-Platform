import { useState } from 'react'
import { api, ApiError } from '../api'
import { Button } from './common'

interface DatasetLoaderProps {
  onLoaded: (result: { count: number; skipped: number; filenames: string[] }) => void
}

export function DatasetLoader({ onLoaded }: DatasetLoaderProps) {
  const [path, setPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(usePath: string | undefined) {
    setLoading(true)
    setError(null)
    try {
      const result = await api.loadDataset(usePath)
      onLoaded(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load dataset.')
    } finally {
      setLoading(false)
    }
  }

  async function useDefaultPath() {
    try {
      const { path: defaultPath } = await api.defaultPath()
      setPath(defaultPath)
      await load(defaultPath)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to resolve default path.')
    }
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <input
        value={path}
        onChange={(event) => setPath(event.target.value)}
        placeholder="Dataset path or ZIP (leave blank for default)"
        className="w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 sm:w-80"
      />
      <div className="flex gap-2">
        <Button onClick={() => load(path || undefined)} disabled={loading}>
          {loading ? 'Loading…' : 'Load dataset'}
        </Button>
        <Button variant="secondary" onClick={useDefaultPath} disabled={loading}>
          Use default
        </Button>
      </div>
      {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
    </div>
  )
}
