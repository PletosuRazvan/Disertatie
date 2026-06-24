import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../api/api'
import InfoTooltip from '../components/InfoTooltip'
import styles from './Predictions.module.css'

const OUTCOME_LABEL = {
  H: 'Home win',
  D: 'Draw',
  A: 'Away win',
}

export default function Predictions() {
  const { isLoggedIn } = useAuth()
  const [teams, setTeams] = useState([])
  const [home, setHome] = useState('')
  const [away, setAway] = useState('')
  const [result, setResult] = useState(null)
  const [loadingTeams, setLoadingTeams] = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/predictions/teams')
      .then(({ data }) => setTeams(data))
      .catch(() => setError('The prediction model is not available yet.'))
      .finally(() => setLoadingTeams(false))
  }, [])

  async function handlePredict(e) {
    e.preventDefault()
    setError('')
    setResult(null)
    if (!home || !away) {
      setError('Please select both teams.')
      return
    }
    if (home === away) {
      setError('Please select two different teams.')
      return
    }
    setPredicting(true)
    try {
      const { data } = await api.post('/predictions/predict', {
        home_team: home,
        away_team: away,
      })
      setResult(data)
    } catch (err) {
      setError(err.response?.data?.error || 'Prediction failed. Please try again.')
    } finally {
      setPredicting(false)
    }
  }

  const probs = result?.probabilities
  const pct = (v) => `${(v * 100).toFixed(1)}%`

  return (
    <div className="page-wrapper">
      <h1 className="page-title">
        Match <span>Predictions</span>
        <InfoTooltip label="How predictions work">
          Pick any <strong>home and away team</strong> and the model estimates the chance
          of a <strong>home win, draw or away win</strong>, along with the most likely
          scoreline and expected goals. It learns from <strong>thousands of past matches</strong>,
          weighing each side's recent form, attack and defence. Probabilities always add up
          to 100%.
        </InfoTooltip>
      </h1>

      {!isLoggedIn && (
        <div className={styles.guestBanner}>
          You are browsing as a guest. <a href="/login">Log in</a> to save your predictions to your history.
        </div>
      )}

      {error && <div className={styles.errorBanner}>{error}</div>}

      <form className={`card ${styles.predictForm}`} onSubmit={handlePredict}>
        <div className={styles.selectRow}>
          <div className={styles.selectGroup}>
            <label>Home team</label>
            <select
              className="form-control"
              value={home}
              onChange={(e) => setHome(e.target.value)}
              disabled={loadingTeams}
            >
              <option value="">{loadingTeams ? 'Loading…' : 'Select home team'}</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <span className={styles.vsLabel}>vs</span>

          <div className={styles.selectGroup}>
            <label>Away team</label>
            <select
              className="form-control"
              value={away}
              onChange={(e) => setAway(e.target.value)}
              disabled={loadingTeams}
            >
              <option value="">{loadingTeams ? 'Loading…' : 'Select away team'}</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <button
          className="btn btn-primary"
          style={{ justifyContent: 'center' }}
          disabled={predicting || loadingTeams}
        >
          {predicting ? 'Predicting…' : 'Predict'}
        </button>
      </form>

      {result && (
        <div className={`card ${styles.resultCard}`}>
          <div className={styles.resultHeader}>
            <span className={styles.resultTeam}>{result.home_team}</span>
            <span className={styles.resultScore}>vs</span>
            <span className={styles.resultTeam}>{result.away_team}</span>
          </div>

          <div className={styles.verdict}>
            Most likely outcome: <strong>{OUTCOME_LABEL[result.predicted_result]}</strong>
          </div>

          <div className={styles.bars}>
            <ProbBar label={`${result.home_team} win`} value={probs.H} color="var(--accent)" pct={pct} />
            <ProbBar label="Draw" value={probs.D} color="#f0b400" pct={pct} />
            <ProbBar label={`${result.away_team} win`} value={probs.A} color="#4f9dff" pct={pct} />
          </div>

          <div className={styles.expected}>
            Expected goals: {result.home_team} {result.expected_goals.home} · {result.away_team} {result.expected_goals.away}
          </div>

          {result.card_adjustment?.applied && (
            <div className={styles.cardNote}>
              ⚠ Score adjusted for projected red-card risk
              ({result.home_team} {Math.round(result.card_adjustment.home_red_risk * 100)}% ·
              {' '}{result.away_team} {Math.round(result.card_adjustment.away_red_risk * 100)}%).
              Base xG was {result.base_expected_goals.home} – {result.base_expected_goals.away}.
            </div>
          )}

          {result.match_stats && (
            <div className={styles.statsBlock}>
              <h3 className={styles.statsTitle}>Projected match statistics</h3>
              <div className={styles.statsTeams}>
                <span className={styles.statsTeamName}>{result.home_team}</span>
                <span className={styles.statsMetricHead}></span>
                <span className={styles.statsTeamName}>{result.away_team}</span>
              </div>
              <StatRow label="Shots" home={result.match_stats.home.shots} away={result.match_stats.away.shots} />
              <StatRow label="On target" home={result.match_stats.home.sot} away={result.match_stats.away.sot} />
              <StatRow label="Corners" home={result.match_stats.home.corners} away={result.match_stats.away.corners} />
              <StatRow label="Fouls" home={result.match_stats.home.fouls} away={result.match_stats.away.fouls} />
              <StatRow label="Offsides" home={result.match_stats.home.offsides} away={result.match_stats.away.offsides} />
              <StatRow label="🟨 Yellows" home={result.match_stats.home.yellows} away={result.match_stats.away.yellows} />
              <StatRow label="🟥 Reds" home={result.match_stats.home.reds} away={result.match_stats.away.reds} />
              <div className={styles.statsFootnote}>
                Estimated from each team's recent home/away form. Throw-ins are not
                recorded by the data source.
              </div>
            </div>
          )}

          {isLoggedIn && (
            <div className={styles.savedNote}>✔ Saved to your prediction history.</div>
          )}
        </div>
      )}
    </div>
  )
}

function ProbBar({ label, value, color, pct }) {
  return (
    <div className={styles.barRow}>
      <span className={styles.barLabel}>{label}</span>
      <div className={styles.barTrack}>
        <div className={styles.barFill} style={{ width: pct(value), background: color }} />
      </div>
      <span className={styles.barValue}>{pct(value)}</span>
    </div>
  )
}

function StatRow({ label, home, away }) {
  const total = (Number(home) + Number(away)) || 1
  const homePct = (Number(home) / total) * 100
  return (
    <div className={styles.statRow}>
      <span className={styles.statHome}>{home}</span>
      <div className={styles.statBarTrack}>
        <div className={styles.statBarHome} style={{ width: `${homePct}%` }} />
        <div className={styles.statBarAway} style={{ width: `${100 - homePct}%` }} />
      </div>
      <span className={styles.statAway}>{away}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  )
}
