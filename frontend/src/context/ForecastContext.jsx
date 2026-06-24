import { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react'
import api from '../api/api'

const ForecastContext = createContext(null)

const NEXT_SEASON = '2026/27'
const MAX_RUNS = 10000
const CALIB_KEY = 'epl_forecast_ms_per_run'
const DEFAULT_MS_PER_RUN = 90   // first-run guess; refined after each completed run
const MIN_MS_PER_RUN = 5
const MAX_MS_PER_RUN = 2000

function clampRuns(v) {
  const n = parseInt(v, 10)
  if (Number.isNaN(n)) return 5
  return Math.max(5, Math.min(n, MAX_RUNS))
}

function loadMsPerRun() {
  const v = parseFloat(localStorage.getItem(CALIB_KEY))
  if (Number.isNaN(v) || v <= 0) return DEFAULT_MS_PER_RUN
  return Math.min(Math.max(v, MIN_MS_PER_RUN), MAX_MS_PER_RUN)
}

export function ForecastProvider({ children }) {
  const [seasons, setSeasons] = useState([NEXT_SEASON])
  const [season, setSeason]   = useState(NEXT_SEASON)
  const [runs, setRuns]       = useState(1000)
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [startedAt, setStartedAt] = useState(null)   // ms timestamp of current run
  const [etaMs, setEtaMs]     = useState(0)          // estimated total duration
  const [progress, setProgress] = useState({ done: 0, total: 0 })  // simulated seasons

  const msPerRun = useRef(loadMsPerRun())
  const abortRef = useRef(null)

  // Load the available seasons once for the whole app session.
  useEffect(() => {
    api.get('/results/seasons')
      .then(({ data }) => setSeasons([NEXT_SEASON, ...data]))
      .catch(() => setSeasons([NEXT_SEASON]))
  }, [])

  const estimateMs = useCallback((nRuns) => {
    return Math.max(500, clampRuns(nRuns) * msPerRun.current)
  }, [])

  const runForecast = useCallback(() => {
    const safeRuns = clampRuns(runs)
    setRuns(safeRuns)
    setError('')
    setData(null)
    setProgress({ done: 0, total: safeRuns })
    setLoading(true)
    const begin = Date.now()
    setStartedAt(begin)
    setEtaMs(estimateMs(safeRuns))

    const controller = new AbortController()
    abortRef.current = controller

    const user = JSON.parse(localStorage.getItem('epl_user') || 'null')

    ;(async () => {
      try {
        const res = await fetch('/api/predictions/simulate-batch-stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(user?.token ? { Authorization: `Bearer ${user.token}` } : {}),
          },
          body: JSON.stringify({ season, runs: safeRuns }),
          signal: controller.signal,
        })
        if (!res.ok) {
          let msg = 'Forecast failed.'
          try { msg = (await res.json())?.error || msg } catch { /* ignore */ }
          throw new Error(msg)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let finalResult = null
        // Throughput is measured from the first progress event so the one-off
        // startup latency (cold start, model load) doesn't inflate the estimate.
        let calibAt = 0
        let calibDone = 0

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let nl
          while ((nl = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, nl).trim()
            buffer = buffer.slice(nl + 1)
            if (!line || line.startsWith(':')) continue
            const json = line.startsWith('data:') ? line.slice(5).trim() : line
            if (!json) continue
            const msg = JSON.parse(json)
            if (msg.type === 'progress') {
              setProgress({ done: msg.done, total: msg.total })
              if (calibAt === 0) {
                // Anchor at the first event and seed a rough ETA from total elapsed
                // (includes startup) so the countdown is never stuck at 0.
                calibAt = Date.now()
                calibDone = msg.done
                if (msg.done > 0) {
                  const rough = (Date.now() - begin) / msg.done
                  setEtaMs(Math.min(Math.max(rough, MIN_MS_PER_RUN), MAX_MS_PER_RUN) * safeRuns)
                }
              } else if (msg.done > calibDone) {
                // Steady-state cost per run, measured since the anchor.
                const live = (Date.now() - calibAt) / (msg.done - calibDone)
                const clamped = Math.min(Math.max(live, MIN_MS_PER_RUN), MAX_MS_PER_RUN)
                msPerRun.current = clamped
                localStorage.setItem(CALIB_KEY, String(clamped))
                setEtaMs(clamped * safeRuns)
              }
            } else if (msg.type === 'result') {
              finalResult = msg.result
            }
          }
        }

        if (finalResult) {
          setData(finalResult)
          setProgress({ done: safeRuns, total: safeRuns })
          // Persist the steady-state per-run cost (excludes startup latency).
          if (calibAt > 0 && safeRuns > calibDone) {
            const actual = (Date.now() - calibAt) / (safeRuns - calibDone)
            const clamped = Math.min(Math.max(actual, MIN_MS_PER_RUN), MAX_MS_PER_RUN)
            msPerRun.current = clamped
            localStorage.setItem(CALIB_KEY, String(clamped))
          }
        }
      } catch (err) {
        // Cancelled requests are not errors.
        if (err?.name !== 'AbortError') {
          setError(err?.message || 'Forecast failed.')
        }
      } finally {
        setLoading(false)
        setStartedAt(null)
        abortRef.current = null
      }
    })()
  }, [season, runs, estimateMs])

  const cancelForecast = useCallback(() => {
    if (abortRef.current) abortRef.current.abort()
  }, [])

  const value = {
    seasons, season, setSeason,
    runs, setRuns,
    data, loading, error,
    startedAt, etaMs,
    progress,
    runForecast, cancelForecast,
    estimateMs,
  }

  return (
    <ForecastContext.Provider value={value}>
      {children}
    </ForecastContext.Provider>
  )
}

export function useForecast() {
  return useContext(ForecastContext)
}
