import { useState, useEffect, useMemo } from 'react'
import { useForecast } from '../context/ForecastContext'
import { useAuth } from '../context/AuthContext'
import InfoTooltip from '../components/InfoTooltip'
import styles from './Forecast.module.css'

const NEXT_SEASON = '2026/27'
const RUN_PRESETS = [100, 500, 1000, 2000, 5000, 10000]
const MAX_RUNS = 10000

function clampRuns(v) {
  const n = parseInt(v, 10)
  if (Number.isNaN(n)) return 5
  return Math.max(5, Math.min(n, MAX_RUNS))
}

function fmtDuration(ms) {
  const total = Math.max(0, Math.round(ms / 1000))
  if (total < 60) return `${total}s`
  const m = Math.floor(total / 60)
  const s = total % 60
  return s ? `${m}m ${s}s` : `${m}m`
}

const COLUMNS = [
  { key: 'team',       label: 'Team',   numeric: false },
  { key: 'title_count', label: 'Titles', numeric: true, bar: 'gold', barPct: 'title_pct' },
  { key: 'top4_count',  label: 'Top 4',  numeric: true, bar: 'cl', barPct: 'top4_pct' },
  { key: 'top10_count', label: 'Top 10', numeric: true, bar: 'mid', barPct: 'top10_pct' },
  { key: 'releg_count', label: 'Relegations', numeric: true, bar: 'rel', barPct: 'releg_pct' },
  { key: 'avg_points', label: 'Avg Pts', numeric: true },
  { key: 'avg_position', label: 'Avg Pos', numeric: true },
  { key: 'best_position', label: 'Best', numeric: true },
  { key: 'worst_position', label: 'Worst', numeric: true },
  { key: 'avg_yellows', label: 'Yel/Season', numeric: true },
  { key: 'avg_reds', label: 'Red/Season', numeric: true },
  { key: 'avg_corners', label: 'Cor/Match', numeric: true },
]

// Columns where a smaller value is better, so the first click sorts ascending.
const ASC_FIRST = new Set(['avg_position', 'best_position', 'worst_position'])

export default function Forecast() {
  const {
    seasons, season, setSeason,
    runs, setRuns,
    data, loading, error,
    startedAt, etaMs,
    progress,
    runForecast, cancelForecast,
    estimateMs,
  } = useForecast()

  const { isLoggedIn } = useAuth()

  const [sortKey, setSortKey] = useState('title_count')
  const [sortDir, setSortDir] = useState('desc')
  const [now, setNow] = useState(Date.now())

  // Keep the elapsed/remaining timer live, even after navigating away and back.
  useEffect(() => {
    if (!loading || !startedAt) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [loading, startedAt])

  function toggleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(ASC_FIRST.has(key) ? 'asc' : key === 'team' ? 'asc' : 'desc')
    }
  }

  const sortedTable = useMemo(() => {
    if (!data?.table) return []
    const rows = [...data.table]
    rows.sort((a, b) => {
      let av = a[sortKey]
      let bv = b[sortKey]
      if (sortKey === 'team') {
        av = String(av).toLowerCase()
        bv = String(bv).toLowerCase()
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return sortDir === 'asc' ? av - bv : bv - av
    })
    return rows
  }, [data, sortKey, sortDir])

  const elapsedMs   = loading && startedAt ? now - startedAt : 0
  const totalRuns   = progress.total || clampRuns(runs)
  const doneRuns    = Math.min(progress.done, totalRuns)
  const progressPct = totalRuns > 0 ? Math.min(100, (doneRuns / totalRuns) * 100) : 0

  // Once a few seasons are done, project remaining time from observed throughput.
  const remainingMs = (() => {
    if (!loading) return 0
    if (doneRuns >= 2 && elapsedMs > 0) {
      const msPerRun = elapsedMs / doneRuns
      return Math.max(0, Math.round((totalRuns - doneRuns) * msPerRun))
    }
    return Math.max(0, etaMs - elapsedMs)
  })()

  return (
    <div className="page-wrapper">
      <h1 className="page-title">
        Season <span>Forecast</span>
        <InfoTooltip label="How the forecast works">
          Runs the whole season <strong>thousands of times</strong> (a Monte-Carlo
          simulation) and counts how often each team wins the title, finishes top 4,
          top 10, or gets relegated — turning many random seasons into{' '}
          <strong>probabilities</strong>. The <strong>next season ({NEXT_SEASON})</strong>{' '}
          uses the real fetched fixtures. More runs give smoother, more reliable odds
          but take longer.
        </InfoTooltip>
      </h1>

      {!isLoggedIn && (
        <div className={styles.guestBanner}>
          You are browsing as a guest. <a href="/login">Log in</a> to save your forecasts to your history.
        </div>
      )}

      <div className={styles.toolbar}>
        <label className={styles.field}>
          <span>Season</span>
          <select
            className="form-control"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            disabled={loading}
          >
            {seasons.map((s) => (
              <option key={s} value={s}>
                {s === NEXT_SEASON ? `${s} — next season` : s}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>Simulations (max {MAX_RUNS.toLocaleString()})</span>
          <input
            type="number"
            className="form-control"
            min={5}
            max={MAX_RUNS}
            value={runs}
            onChange={(e) => setRuns(e.target.value)}
            onBlur={(e) => setRuns(clampRuns(e.target.value))}
            disabled={loading}
          />
        </label>

        <div className={styles.presets}>
          {RUN_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className={`${styles.preset} ${Number(runs) === p ? styles.presetActive : ''}`}
              onClick={() => setRuns(p)}
              disabled={loading}
            >
              {p.toLocaleString()}
            </button>
          ))}
        </div>

        <button className="btn btn-primary" onClick={runForecast} disabled={loading}>
          {loading ? 'Running…' : data ? '↻ Re-run' : '▶ Run forecast'}
        </button>
        {loading && (
          <button className="btn btn-danger" onClick={cancelForecast}>
            ✕ Cancel
          </button>
        )}
      </div>

      {!loading && (
        <p className={styles.hint}>
          Estimated time for {clampRuns(runs).toLocaleString()} runs: ~{fmtDuration(estimateMs(runs))}.
          More runs = smoother probabilities but longer wait.
        </p>
      )}

      {loading && (
        <div className={styles.loading}>
          <div className={styles.loadingHead}>
            <span>
              Simulating seasons… <strong>{doneRuns.toLocaleString()} / {totalRuns.toLocaleString()}</strong>
            </span>
            <span className={styles.timer}>
              {Math.round(progressPct)}% · {fmtDuration(elapsedMs)} elapsed · {doneRuns < 1 ? 'estimating…' : `~${fmtDuration(remainingMs)} left`}
            </span>
          </div>
          <div className={styles.progressTrack}>
            <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
          </div>
          <p className={styles.loadingNote}>
            You can switch tabs — the forecast keeps running and will be here when you return.
          </p>
        </div>
      )}

      {error && <div className={styles.errorBanner}>{error}</div>}

      {data && !loading && (
        <>
          <div className={styles.summary}>
            <span className={styles.tag}>{data.season}</span>
            <span className={styles.tagMuted}>{data.runs.toLocaleString()} simulations</span>
            <span className={styles.tagMuted}>{data.teams.length} teams</span>
          </div>

          <div className="card table-wrapper">
            <table className={styles.table}>
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      className={`${styles.th} ${c.numeric ? styles.thNum : ''} ${sortKey === c.key ? styles.thActive : ''}`}
                      onClick={() => toggleSort(c.key)}
                    >
                      {c.label}
                      <span className={styles.sortArrow}>
                        {sortKey === c.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ⇅'}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedTable.map((r) => (
                  <tr key={r.team}>
                    <td className={styles.teamCell}>{r.team}</td>
                    {COLUMNS.slice(1).map((c) => (
                      <td key={c.key} className={styles.numCell}>
                        {c.bar ? (
                          <div className={styles.barWrap}>
                            <div
                              className={`${styles.bar} ${styles[`bar_${c.bar}`]}`}
                              style={{ width: `${Math.min(c.barPct ? r[c.barPct] : r[c.key], 100)}%` }}
                            />
                            <span className={styles.barLabel}>
                              {r[c.key]}{c.suffix || ''}
                            </span>
                          </div>
                        ) : (
                          <>{r[c.key]}{c.suffix || ''}</>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
