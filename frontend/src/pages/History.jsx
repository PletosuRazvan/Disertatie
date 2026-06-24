import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/api'
import { useAuth } from '../context/AuthContext'
import styles from './History.module.css'

const OUTCOME_LABEL = { H: 'Home Win', D: 'Draw', A: 'Away Win' }
const OUTCOME_CLASS  = { H: 'badge-h', D: 'badge-d', A: 'badge-a' }

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
              {open === s.id ? 'Hide table' : 'View table'}
            </button>
          </div>
          <div className={styles.date}>{fmtDate(s.timestamp)}</div>

          {open === s.id && (
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
          )}
        </div>
      ))}
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
                  <tr><th>Team</th><th>Titles</th><th>Top 4</th><th>Relegations</th><th>Avg Pts</th></tr>
                </thead>
                <tbody>
                  {[...f.table]
                    .sort((a, b) => (b.title_count ?? 0) - (a.title_count ?? 0))
                    .map((r) => (
                      <tr key={r.team}>
                        <td style={{ fontWeight: 500 }}>{r.team}</td>
                        <td>{r.title_count}</td>
                        <td>{r.top4_count}</td>
                        <td>{r.releg_count}</td>
                        <td>{r.avg_points}</td>
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
