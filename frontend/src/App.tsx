import { useState } from 'react'
import { DatasetLoader } from './components/DatasetLoader'
import { SummaryPanel } from './components/SummaryPanel'
import { SearchPanel } from './components/SearchPanel'
import { ExperimentsPanel } from './components/ExperimentsPanel'

type Tab = 'summary' | 'search' | 'experiments'

interface DatasetState {
  loaded: boolean
  count: number
  skipped: number
  filenames: string[]
}

const initialDataset: DatasetState = { loaded: false, count: 0, skipped: 0, filenames: [] }

const TABS: { id: Tab; label: string }[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'search', label: 'Search' },
  { id: 'experiments', label: 'Experiments' },
]

function App() {
  const [dataset, setDataset] = useState<DatasetState>(initialDataset)
  const [tab, setTab] = useState<Tab>('summary')

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:px-6">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold">NHMFL Condensed Matter Analysis Platform</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {dataset.loaded
                ? `${dataset.count} experiment${dataset.count === 1 ? '' : 's'} loaded${
                    dataset.skipped ? ` · ${dataset.skipped} skipped` : ''
                  }`
                : 'Load a dataset to get started.'}
            </p>
          </div>
          <DatasetLoader
            onLoaded={(result) =>
              setDataset({
                loaded: true,
                count: result.count,
                skipped: result.skipped,
                filenames: result.filenames,
              })
            }
          />
        </div>
      </header>

      <nav className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl gap-1 px-4 sm:px-6">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`border-b-2 px-3 py-3 text-sm font-medium transition-colors ${
                tab === id
                  ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {tab === 'summary' && <SummaryPanel datasetLoaded={dataset.loaded} />}
        {tab === 'search' && <SearchPanel datasetLoaded={dataset.loaded} />}
        {tab === 'experiments' &&
          (dataset.loaded ? (
            <ExperimentsPanel filenames={dataset.filenames} />
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Load a dataset above to browse experiments.
            </p>
          ))}
      </main>
    </div>
  )
}

export default App
