import { useState, useEffect } from 'react'
import api from '../api/api'
import styles from './Results.module.css'

const RESULT_LABEL = { H: 'Home Win', A: 'Away Win', D: 'Draw' }
const RESULT_CLASS  = { H: 'badge-h', A: 'badge-a', D: 'badge-d' }

export default function Results() {
  const [seasons, setSeasons]   = useState([])
  const [season,  setSeason]    = useState('')
  const [results, setResults]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [search,  setSearch]    = useState('')
  const [page,    setPage]      = useState(1)
  const [total,   setTotal]     = useState(0)
  const LIMIT = 20

  // Load the list of available seasons once, then default to the most recent.
  useEffect(() => {
    api.get('/results/seasons')
      .then(({ data }) => {
        setSeasons(data)
        if (data.length) setSeason(data[0])
      })
      .catch(() => setSeasons([]))
  }, [])

  useEffect(() => {
    if (!season) return
    setLoading(true)
    api.get('/results/', { params: { page, limit: LIMIT, team: search, season } })
      .then(({ data }) => { setResults(data.results); setTotal(data.total) })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [page, search, season])

  function handleSearch(e) {
    setSearch(e.target.value)
    setPage(1)
  }

  function handleSeason(e) {
    setSeason(e.target.value)
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil(total / LIMIT))

  return (
    <div className="page-wrapper">
      <h1 className="page-title">Match <span>Results</span></h1>

      <div className={styles.toolbar}>
        <label className={styles.field}>
          <span>Season</span>
          <select
            className="form-control"
            value={season}
            onChange={handleSeason}
            disabled={!seasons.length}
          >
            {seasons.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>Filter by team</span>
          <input
            className="form-control"
            placeholder="e.g. Arsenal…"
            value={search}
            onChange={handleSearch}
          />
        </label>

        <span className={styles.count}>{total} matches</span>
      </div>

      <div className="card table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Home</th>
              <th style={{ textAlign: 'center' }}>Score</th>
              <th>Away</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading…</td></tr>
            ) : results.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>No results found.</td></tr>
            ) : results.map((r) => (
              <tr key={r.id}>
                <td style={{ color: 'var(--text-muted)', fontSize: '.85rem' }}>{r.date}</td>
                <td style={{ fontWeight: r.result === 'H' ? 600 : 400 }}>{r.home_team}</td>
                <td style={{ textAlign: 'center', fontWeight: 700 }}>{r.home_goals} – {r.away_goals}</td>
                <td style={{ fontWeight: r.result === 'A' ? 600 : 400 }}>{r.away_team}</td>
                <td><span className={RESULT_CLASS[r.result]}>{RESULT_LABEL[r.result]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className={styles.pagination}>
        <button className="btn btn-outline" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>← Prev</button>
        <span style={{ color: 'var(--text-muted)', fontSize: '.9rem' }}>Page {page} / {totalPages}</span>
        <button className="btn btn-outline" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Next →</button>
      </div>
    </div>
  )
}
