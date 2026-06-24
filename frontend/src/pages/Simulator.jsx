import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../api/api'
import InfoTooltip from '../components/InfoTooltip'
import styles from './Simulator.module.css'

const CL_ZONE  = [1, 2, 3, 4]
const EL_ZONE  = [5]
const REL_ZONE = [18, 19, 20]
const RESULT_CLASS = { H: styles.badgeH, A: styles.badgeA, D: styles.badgeD }
const RESULT_LABEL = { H: '1', D: 'X', A: '2' }
const NEXT_SEASON = '2026/27'

function rowClass(pos) {
  if (CL_ZONE.includes(pos))  return styles.cl
  if (EL_ZONE.includes(pos))  return styles.el
  if (REL_ZONE.includes(pos)) return styles.rel
  return ''
}

export default function Simulator() {
  const { isLoggedIn } = useAuth()
  const [sim, setSim]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')
  const [round, setRound]   = useState(0)
  const [seasons, setSeasons] = useState([])
  const [season, setSeason]   = useState('')

  useEffect(() => {
    api.get('/results/seasons')
      .then(({ data }) => {
        const all = [NEXT_SEASON, ...data]
        setSeasons(all)
        setSeason(NEXT_SEASON)
      })
      .catch(() => {
        setSeasons([NEXT_SEASON])
        setSeason(NEXT_SEASON)
      })
  }, [])

  function runSimulation() {
    setLoading(true)
    setError('')
    api.post('/predictions/simulate', season ? { season } : {})
      .then(({ data }) => { setSim(data); setRound(0) })
      .catch((err) => setError(err?.response?.data?.error || 'Simulation failed.'))
      .finally(() => setLoading(false))
  }

  const matchday = sim?.matchdays?.[round]

  return (
    <div className="page-wrapper">
      <h1 className="page-title">
        Season <span>Simulator</span>
        <InfoTooltip label="How the simulator works">
          Plays out a single full <strong>38-matchday season</strong>, match by match.
          Each fixture's result is <strong>sampled</strong> from the model's probabilities,
          so the scoreline, the cards and the final table change on <strong>every run</strong>.
          For the <strong>next season ({NEXT_SEASON})</strong> it uses the real fetched
          fixture list; past seasons replay that year's actual teams. Team strength is
          carried over from the previous campaign. Use it to watch one plausible way a
          season could unfold and read the final standings.
        </InfoTooltip>
      </h1>

      {!isLoggedIn && (
        <div className={styles.guestBanner}>
          You are browsing as a guest. <a href="/login">Log in</a> to save your simulations to your history.
        </div>
      )}

      <div className={styles.toolbar}>
        <select
          className="form-control"
          value={season}
          onChange={(e) => setSeason(e.target.value)}
          style={{ width: 'auto' }}
          disabled={loading}
        >
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s === NEXT_SEASON ? `${s} — next season` : s}
            </option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={runSimulation} disabled={loading}>
          {loading ? 'Simulating…' : sim ? '↻ Re-simulate' : '▶ Run simulation'}
        </button>
        {sim && <span className={styles.seasonTag}>Showing {sim.season}</span>}
      </div>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {sim && (
        <div className={styles.grid}>
          {/* Final standings */}
          <div>
            <h2 className={styles.sectionTitle}>Final Standings</h2>
            <div className={styles.legend}>
              <span className={styles.dotCl} /> Champions League
              <span className={styles.dotEl} style={{ marginLeft: '1rem' }} /> Europa League
              <span className={styles.dotRel} style={{ marginLeft: '1rem' }} /> Relegation
            </div>
            <div className="card table-wrapper">
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
                  {sim.standings.map((r) => (
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
          </div>

          {/* Matchday browser */}
          <div>
            <h2 className={styles.sectionTitle}>Results by Matchday</h2>
            <div className={styles.roundNav}>
              <button className="btn btn-outline" onClick={() => setRound((r) => Math.max(0, r - 1))} disabled={round === 0}>← Prev</button>
              <select
                className="form-control"
                value={round}
                onChange={(e) => setRound(Number(e.target.value))}
                style={{ width: 'auto' }}
              >
                {sim.matchdays.map((m, i) => (
                  <option key={i} value={i}>Matchday {m.round}</option>
                ))}
              </select>
              <button className="btn btn-outline" onClick={() => setRound((r) => Math.min(sim.matchdays.length - 1, r + 1))} disabled={round === sim.matchdays.length - 1}>Next →</button>
            </div>

            <div className={`card ${styles.matchList}`}>
              {matchday?.matches.map((m, i) => (
                <div key={i} className={styles.matchRow}>
                  <span className={`${styles.team} ${styles.home} ${m.result === 'H' ? styles.winner : ''}`}>{m.home_team}</span>
                  <span className={styles.score}>{m.home_goals} – {m.away_goals}</span>
                  <span className={`${styles.team} ${styles.away} ${m.result === 'A' ? styles.winner : ''}`}>{m.away_team}</span>
                  <span className={RESULT_CLASS[m.result]}>{RESULT_LABEL[m.result]}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!sim && !loading && (
        <div className={styles.placeholder}>
          Click <strong>Run simulation</strong> to generate a complete season.
        </div>
      )}
    </div>
  )
}
