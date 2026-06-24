import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './Home.module.css'

const RECENT = [
  { id: 1, home: 'Arsenal',       hg: 2, ag: 0, away: 'Wolverhampton',   result: 'H' },
  { id: 2, home: 'Liverpool',     hg: 2, ag: 2, away: 'Ipswich Town',     result: 'D' },
  { id: 3, home: 'Man City',      hg: 2, ag: 0, away: 'Chelsea',          result: 'H' },
  { id: 4, home: 'Nottm Forest',  hg: 1, ag: 0, away: 'Bournemouth',      result: 'H' },
  { id: 5, home: 'Tottenham',     hg: 4, ag: 0, away: 'Everton',          result: 'H' },
]

const STATS = [
  { label: 'Matches in DB', value: '12,500+' },
  { label: 'Seasons',       value: '32' },
  { label: 'Teams',         value: '49' },
  { label: 'Your predictions', value: '—' },
]

export default function Home() {
  const { isLoggedIn, user } = useAuth()

  return (
    <div className="page-wrapper">
      {/* Hero */}
      <section className={styles.hero}>
        <h1>Premier League<br /><span>Predictions Hub</span></h1>
        <p>Analyse historical results, track standings and compete with your own score predictions.</p>
        <div className={styles.heroActions}>
          <Link to="/predictions" className="btn btn-primary">Make Predictions</Link>
          <Link to="/standings"   className="btn btn-outline">2024/25 Table</Link>
        </div>
      </section>

      {/* Stats strip */}
      <div className={styles.statsRow}>
        {STATS.map((s) => (
          <div key={s.label} className={`card ${styles.statCard}`}>
            <span className={styles.statVal}>{isLoggedIn && s.label === 'Your predictions' ? '0' : s.value}</span>
            <span className={styles.statLabel}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Recent results */}
      <section>
        <div className={styles.sectionHeader}>
          <h2 className="page-title" style={{ marginBottom: 0 }}>Recent <span>Results</span></h2>
          <Link to="/results" className="btn btn-outline" style={{ fontSize: '.82rem' }}>View all →</Link>
        </div>
        <div className={styles.resultsList}>
          {RECENT.map((m) => (
            <div key={m.id} className={`card ${styles.matchCard}`}>
              <span className={styles.team} style={{ textAlign: 'right' }}>{m.home}</span>
              <span className={styles.score}>
                {m.hg} – {m.ag}
              </span>
              <span className={styles.team}>{m.away}</span>
              <span className={`badge-${m.result.toLowerCase()} ${styles.badge}`}>
                {m.result === 'H' ? 'HOME' : m.result === 'A' ? 'AWAY' : 'DRAW'}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      {!isLoggedIn && (
        <section className={`card ${styles.ctaBanner}`}>
          <div>
            <h3>Ready to predict?</h3>
            <p style={{ color: 'var(--text-muted)', marginTop: '.3rem' }}>
              Create a free account to save your predictions and track your accuracy.
            </p>
          </div>
          <Link to="/register" className="btn btn-primary">Get Started</Link>
        </section>
      )}
    </div>
  )
}
