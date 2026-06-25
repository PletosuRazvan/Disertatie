import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/api'
import { useAuth } from '../context/AuthContext'
import styles from './History.module.css'

const OUTCOME_LABEL = { H: 'Home Win', D: 'Draw', A: 'Away Win' }
const OUTCOME_CLASS  = { H: 'badge-h', D: 'badge-d', A: 'badge-a' }
const RESULT_LABEL   = { H: '1', D: 'X', A: '2' }
const RESULT_CLASS   = { H: styles.badgeH, D: styles.badgeD, A: styles.badgeA }

const CL_ZONE  = [1, 2, 3, 4]
const EL_ZONE  = [5]
const REL_ZONE = [18, 19, 20]

function rowClass(pos) {
  if (CL_ZONE.includes(pos))  return styles.cl
  if (EL_ZONE.includes(pos))  return styles.el
  if (REL_ZONE.includes(pos)) return styles.rel
  return ''
}

// Same columns as the Forecast page (counts, not percentages, with bars).
const COLUMNS = [
  { key: 'team',           label: 'Team',        numeric: false },
  { key: 'title_count',    label: 'Titles',      numeric: true, bar: 'gold', barPct: 'title_pct' },
  { key: 'top4_count',     label: 'Top 4',       numeric: true, bar: 'cl',   barPct: 'top4_pct' },
  { key: 'top10_count',    label: 'Top 10',      numeric: true, bar: 'mid',  barPct: 'top10_pct' },
  { key: 'releg_count',    label: 'Relegations', numeric: true, bar: 'rel',  barPct: 'releg_pct' },
  { key: 'avg_points',     label: 'Avg Pts',     numeric: true },
  { key: 'avg_position',   label: 'Avg Pos',     numeric: true },
  { key: 'best_position',  label: 'Best',        numeric: true },
  { key: 'worst_position', label: 'Worst',       numeric: true },
  { key: 'avg_yellows',    label: 'Yel/Season',  numeric: true },
  { key: 'avg_reds',       label: 'Red/Season',  numeric: true },
  { key: 'avg_corners',    label: 'Cor/Match',   numeric: true },
]

// Columns where a smaller value is better, so the first click sorts ascending.
const ASC_FIRST = new Set(['avg_position', 'best_position', 'worst_position'])

const TABS = [
  { key: 'predictions',  label: 'Predictions' },
  { key: 'simulations',  label: 'Simulated Seasons' },
  { key: 'forecasts',    label: 'Forecasts' },
]

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function History() {
  const { isLoggedIn } = useAuth()
  const [tab, setTab] = useState('predictions')
  const [predictions, setPredictions] = useState([])
  const [simulations, setSimulations] = useState([])
  const [forecasts, setForecasts]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    if (!isLoggedIn) { setLoading(false); return }
    setLoading(true)
    Promise.all([
      api.get('/predictions/history'),
      api.get('/predictions/history/simulations'),
      api.get('/predictions/history/forecasts'),
    ])
      .then(([p, s, f]) => {
        setPredictions(p.data)
        setSimulations(s.data)
        setForecasts(f.data)
      })
      .catch(() => setError('Could not load your history.'))
      .finally(() => setLoading(false))
  }, [isLoggedIn])

  if (!isLoggedIn) {
    return (
      <div className="page-wrapper">
        <h1 className="page-title">My <span>History</span></h1>
        <div className={styles.empty}>
          Please <Link to="/login" className={styles.link}>log in</Link> to view and
          save your predictions, simulations and forecasts.
        </div>
      </div>
    )
  }

  const counts = {
    predictions: predictions.length,
    simulations: simulations.length,
    forecasts: forecasts.length,
  }

  return (
    <div className="page-wrapper">
      <h1 className="page-title">My <span>History</span></h1>
      <p className={styles.intro}>
        Everything you generate while logged in is saved here automatically —
        your match predictions, simulated seasons and Monte-Carlo forecasts.
      </p>

      <div className={styles.tabs}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            <span className={styles.badge}>{counts[t.key]}</span>
          </button>
        ))}
      </div>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {loading ? (
        <div className={styles.empty}>Loading…</div>
      ) : (
        <>
          {tab === 'predictions' && <Predictions items={predictions} />}
          {tab === 'simulations' && <Simulations items={simulations} />}
          {tab === 'forecasts'   && <Forecasts items={forecasts} />}
        </>
      )}
    </div>
  )
}

function Predictions({ items }) {
  if (!items.length) return <Empty what="predictions" to="/predictions" cta="Make a prediction" />
  return (
    <div className={styles.list}>
      {items.map((p) => {
        const probs = p.probabilities || {}
        return (
          <div key={p.id} className={`card ${styles.card}`}>
            <div className={styles.cardMain}>
              <div className={styles.matchup}>
                <strong>{p.home_team}</strong>
                <span className={styles.vs}>vs</span>
                <strong>{p.away_team}</strong>
              </div>
              <span className={OUTCOME_CLASS[p.predicted_result]}>
                {OUTCOME_LABEL[p.predicted_result]}
              </span>
            </div>
            <div className={styles.probs}>
              <span>Home {Math.round((probs.H ?? 0) * 100)}%</span>
              <span>Draw {Math.round((probs.D ?? 0) * 100)}%</span>
              <span>Away {Math.round((probs.A ?? 0) * 100)}%</span>
            </div>
            <div className={styles.date}>{fmtDate(p.timestamp)}</div>
          </div>
        )
      })}
    </div>
  )
}

function Simulations({ items }) {
  const [open, setOpen] = useState(null)
  if (!items.length) return <Empty what="simulated seasons" to="/simulator" cta="Run a simulation" />
  return (
    <div className={styles.list}>
      {items.map((s) => (
        <div key={s.id} className={`card ${styles.card}`}>
          <div className={styles.cardMain}>
            <div>
              <span className={styles.tagSeason}>{s.season}</span>
              <span className={styles.champion}>🏆 {s.champion}</span>
            </div>
            <button
              className="btn btn-outline"
              onClick={() => setOpen(open === s.id ? null : s.id)}
            >
              {open === s.id ? 'Hide details' : 'View details'}
            </button>
          </div>
          <div className={styles.date}>{fmtDate(s.timestamp)}</div>

          {open === s.id && (
            <>
              <div className={styles.legend}>
                <span className={styles.dotCl} /> Champions League
                <span className={styles.dotEl} style={{ marginLeft: '1rem' }} /> Europa League
                <span className={styles.dotRel} style={{ marginLeft: '1rem' }} /> Relegation
              </div>
              <div className="table-wrapper" style={{ marginTop: '.4rem' }}>
                <table>
                  <thead>
                    <tr>
                      <th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th>
                      <th>L</th><th>GF</th><th>GA</th><th>GD</th><th><strong>Pts</strong></th>
                      <th title="Yellow cards (season total)">Yel</th>
                      <th title="Red cards (season total)">Red</th>
                      <th title="Corners (average per match)">Cor/M</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.standings.map((r) => (
                      <tr key={r.team} className={rowClass(r.pos)}>
                        <td><span className={styles.pos}>{r.pos}</span></td>
                        <td style={{ fontWeight: 500 }}>{r.team}</td>
                        <td>{r.played}</td>
                        <td>{r.won}</td>
                        <td>{r.drawn}</td>
                        <td>{r.lost}</td>
                        <td>{r.gf}</td>
                        <td>{r.ga}</td>
                        <td style={{ color: r.gd >= 0 ? 'var(--accent)' : 'var(--red)' }}>
                          {r.gd > 0 ? `+${r.gd}` : r.gd}
                        </td>
                        <td><strong>{r.points}</strong></td>
                        <td>{r.yellows != null ? Math.round(r.yellows) : '—'}</td>
                        <td>{r.reds != null ? Math.round(r.reds) : '—'}</td>
                        <td>{r.corners_avg ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {s.matchdays?.length > 0 && <MatchdayBrowser matchdays={s.matchdays} />}
            </>
          )}
        </div>
      ))}
    </div>
  )
}

function MatchdayBrowser({ matchdays }) {
  const [round, setRound] = useState(0)
  const md = matchdays[round]
  return (
    <div style={{ marginTop: '1rem' }}>
      <div className={styles.roundNav}>
        <button
          className="btn btn-outline"
          onClick={() => setRound((r) => Math.max(0, r - 1))}
          disabled={round === 0}
        >← Prev</button>
        <select
          className="form-control"
          value={round}
          onChange={(e) => setRound(Number(e.target.value))}
          style={{ width: 'auto' }}
        >
          {matchdays.map((m, i) => (
            <option key={i} value={i}>Matchday {m.round}</option>
          ))}
        </select>
        <button
          className="btn btn-outline"
          onClick={() => setRound((r) => Math.min(matchdays.length - 1, r + 1))}
          disabled={round === matchdays.length - 1}
        >Next →</button>
      </div>
      <div className={`card ${styles.matchList}`}>
        {md?.matches.map((m, i) => (
          <div key={i} className={styles.matchRow}>
            <span className={`${styles.team} ${styles.home} ${m.result === 'H' ? styles.winner : ''}`}>{m.home_team}</span>
            <span className={styles.score}>{m.home_goals} – {m.away_goals}</span>
            <span className={`${styles.team} ${styles.away} ${m.result === 'A' ? styles.winner : ''}`}>{m.away_team}</span>
            <span className={RESULT_CLASS[m.result]}>{RESULT_LABEL[m.result]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Forecasts({ items }) {
  const [open, setOpen] = useState(null)
  if (!items.length) return <Empty what="forecasts" to="/forecast" cta="Run a forecast" />
  return (
    <div className={styles.list}>
      {items.map((f) => (
        <div key={f.id} className={`card ${styles.card}`}>
          <div className={styles.cardMain}>
            <div>
              <span className={styles.tagSeason}>{f.season}</span>
              <span className={styles.tagMuted}>{(f.runs ?? 0).toLocaleString()} runs</span>
              {f.teams?.length > 0 && <span className={styles.tagMuted}>{f.teams.length} teams</span>}
              <span className={styles.champion}>⭐ {f.favourite}</span>
            </div>
            <button
              className="btn btn-outline"
              onClick={() => setOpen(open === f.id ? null : f.id)}
            >
              {open === f.id ? 'Hide table' : 'View table'}
            </button>
          </div>
          <div className={styles.date}>{fmtDate(f.timestamp)}</div>

          {open === f.id && <ForecastTable table={f.table} />}
        </div>
      ))}
    </div>
  )
}

// Mirrors the Forecast page table exactly: sortable columns, counts (not %)
// with proportional bars.
function ForecastTable({ table }) {
  const [sortKey, setSortKey] = useState('title_count')
  const [sortDir, setSortDir] = useState('desc')

  function toggleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(ASC_FIRST.has(key) ? 'asc' : key === 'team' ? 'asc' : 'desc')
    }
  }

  const sorted = [...(table || [])].sort((a, b) => {
    let av = a[sortKey]
    let bv = b[sortKey]
    if (sortKey === 'team') {
      av = String(av).toLowerCase()
      bv = String(bv).toLowerCase()
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    }
    return sortDir === 'asc' ? (av ?? 0) - (bv ?? 0) : (bv ?? 0) - (av ?? 0)
  })

  return (
    <div className="card table-wrapper" style={{ marginTop: '.8rem' }}>
      <table className={styles.fcTable}>
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
          {sorted.map((r) => (
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
                    <>{r[c.key] ?? '—'}{c.suffix || ''}</>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


function Empty({ what, to, cta }) {
  return (
    <div className={styles.empty}>
      No {what} saved yet.{' '}
      <Link to={to} className={styles.link}>{cta} →</Link>
    </div>
  )
}
