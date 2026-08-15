import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { DatasetAlias } from '../types'
import { Button } from './common'

interface DatasetLoaderProps {
  onLoaded: (result: { count: number; skipped: number; filenames: string[] }) => void
}

export function DatasetLoader({ onLoaded }: DatasetLoaderProps) {
  const [path, setPath] = useState('')
  const [aliases, setAliases] = useState<DatasetAlias[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .datasetAliases()
      .then((response) => setAliases(response.aliases))
      .catch(() => setAliases([]))
  }, [])

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

  return (
    <div className="flex flex-col gap-3">
      {aliases.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {aliases.map((alias) => (
            <Button
              key={alias.name}
              variant="secondary"
              disabled={loading}
              onClick={() => {
                setPath(alias.name)
                load(alias.name)
              }}
            >
              {alias.label}
            </Button>
          ))}
        </div>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="Dataset name (e.g. nhmfl2020) or full path"
          className="w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 sm:w-80"
        />
        <Button onClick={() => load(path || undefined)} disabled={loading}>
          {loading ? 'Loading…' : 'Load dataset'}
        </Button>
      </div>
      {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
    </div>
  )
}
