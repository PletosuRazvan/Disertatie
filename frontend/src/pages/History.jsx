import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/api'
import { useAuth } from '../context/AuthContext'
import styles from './History.module.css'

const OUTCOME_LABEL = { H: 'Home Win', D: 'Draw', A: 'Away Win' }
const OUTCOME_CLASS  = { H: 'badge-h', D: 'badge-d', A: 'badge-a' }
const RESULT_LABEL   = { H: '1', D: 'X', A: '2' }
const RESULT_CLASS   = { H: 'badge-h', D: 'badge-d', A: 'badge-a' }

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
              <div className="table-wrapper" style={{ marginTop: '.8rem' }}>
                <table>
                  <thead>
                    <tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th></tr>
                  </thead>
                  <tbody>
                    {s.standings.map((r) => (
                      <tr key={r.team}>
                        <td>{r.pos}</td>
                        <td style={{ fontWeight: 500 }}>{r.team}</td>
                        <td>{r.played}</td>
                        <td>{r.won}</td>
                        <td>{r.drawn}</td>
                        <td>{r.lost}</td>
                        <td style={{ color: r.gd >= 0 ? 'var(--accent)' : 'var(--red)' }}>
                          {r.gd > 0 ? `+${r.gd}` : r.gd}
                        </td>
                        <td><strong>{r.points}</strong></td>
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
      <div className={styles.matchList}>
        {md?.matches.map((m, i) => (
          <div key={i} className={styles.matchRow}>
            <span style={{ fontWeight: m.result === 'H' ? 700 : 400, textAlign: 'right', flex: 1 }}>{m.home_team}</span>
            <span className={styles.matchScore}>{m.home_goals} – {m.away_goals}</span>
            <span style={{ fontWeight: m.result === 'A' ? 700 : 400, flex: 1 }}>{m.away_team}</span>
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

          {open === f.id && (
            <div className="table-wrapper" style={{ marginTop: '.8rem' }}>
              <table>
                <thead>
                  <tr>
                    <th>Team</th><th>Title%</th><th>Top 4%</th><th>Top 10%</th>
                    <th>Releg%</th><th>Avg Pts</th><th>Avg Pos</th><th>Best</th><th>Worst</th>
                  </tr>
                </thead>
                <tbody>
                  {[...f.table]
                    .sort((a, b) => (b.title_pct ?? 0) - (a.title_pct ?? 0))
                    .map((r) => (
                      <tr key={r.team}>
                        <td style={{ fontWeight: 500 }}>{r.team}</td>
                        <td>{r.title_pct ?? r.title_count}%</td>
                        <td>{r.top4_pct ?? r.top4_count}%</td>
                        <td>{r.top10_pct != null ? `${r.top10_pct}%` : '—'}</td>
                        <td>{r.releg_pct ?? r.releg_count}%</td>
                        <td>{r.avg_points}</td>
                        <td>{r.avg_position ?? '—'}</td>
                        <td>{r.best_position ?? '—'}</td>
                        <td>{r.worst_position ?? '—'}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
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
