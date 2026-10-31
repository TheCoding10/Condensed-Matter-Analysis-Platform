import { useEffect, useState, type FormEvent, type PropsWithChildren } from 'react'
import { api, ApiError, setPassword } from '../api'
import { Button, Card, Spinner } from './common'

type GateState = 'checking' | 'open' | 'locked'

// Shows a password screen when the backend requires one (the hosted
// deployment); renders the app straight away for a local backend.
export function PasswordGate({ children }: PropsWithChildren) {
  const [state, setState] = useState<GateState>('checking')
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function check(): Promise<boolean> {
    try {
      const result = await api.authCheck()
      return !result.required || result.ok
    } catch (err) {
      // An unreachable backend is reported by the app's own error banners.
      if (err instanceof ApiError && err.status === 0) return true
      throw err
    }
  }

  useEffect(() => {
    check()
      .then((ok) => setState(ok ? 'open' : 'locked'))
      .catch(() => setState('open'))
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setPassword(input)
    try {
      if (await check()) {
        setState('open')
      } else {
        setError('Wrong password.')
      }
    } catch {
      setError('Could not check the password. Try again in a minute.')
    }
  }

  if (state === 'checking') return <Spinner label="Connecting to the analysis server… (can take a minute if it was asleep)" />
  if (state === 'open') return <>{children}</>

  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <Card>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <h1 className="text-lg font-semibold">NHMFL Condensed Matter Analysis Platform</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Enter the password to continue.</p>
          <input
            type="password"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            autoFocus
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={!input}>
            Continue
          </Button>
        </form>
      </Card>
    </div>
  )
}
