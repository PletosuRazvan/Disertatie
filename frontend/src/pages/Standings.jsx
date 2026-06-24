import { useState, useEffect } from 'react'
import api from '../api/api'
import styles from './Standings.module.css'

const CL_ZONE   = [1, 2, 3, 4]
const EL_ZONE   = [5]
const REL_ZONE  = [18, 19, 20]

function rowClass(pos) {
  if (CL_ZONE.includes(pos))  return styles.cl
  if (EL_ZONE.includes(pos))  return styles.el
  if (REL_ZONE.includes(pos)) return styles.rel
  return ''
}

export default function Standings() {
  const [standings, setStandings] = useState([])
  const [seasons, setSeasons]     = useState([])
  const [season, setSeason]       = useState('')
  const [loading, setLoading]     = useState(true)

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
    api.get('/standings/', { params: { season } })
      .then(({ data }) => setStandings(data.standings))
      .catch(() => setStandings([]))
      .finally(() => setLoading(false))
  }, [season])

  return (
    <div className="page-wrapper">
      <div className={styles.header}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>
          Premier League <span>Standings</span>
        </h1>
        <select className="form-control" value={season} onChange={(e) => setSeason(e.target.value)} style={{ width: 'auto' }}>
          {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className={styles.legend}>
        <span className={styles.dotCl} /> Champions League
        <span className={styles.dotEl} style={{ marginLeft: '1.2rem' }} /> Europa League
        <span className={styles.dotRel} style={{ marginLeft: '1.2rem' }} /> Relegation
      </div>

      <div className="card table-wrapper">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Team</th>
              <th title="Played">P</th>
              <th title="Won">W</th>
              <th title="Drawn">D</th>
              <th title="Lost">L</th>
              <th title="Goals For">GF</th>
              <th title="Goals Against">GA</th>
              <th title="Goal Difference">GD</th>
              <th title="Points"><strong>Pts</strong></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading…</td></tr>
            ) : standings.map((row) => (
              <tr key={row.pos} className={rowClass(row.pos)}>
                <td><span className={styles.pos}>{row.pos}</span></td>
                <td style={{ fontWeight: 500 }}>{row.team}</td>
                <td>{row.played}</td>
                <td>{row.won}</td>
                <td>{row.drawn}</td>
                <td>{row.lost}</td>
                <td>{row.gf}</td>
                <td>{row.ga}</td>
                <td style={{ color: row.gd >= 0 ? 'var(--accent)' : 'var(--red)' }}>
                  {row.gd > 0 ? `+${row.gd}` : row.gd}
                </td>
                <td><strong>{row.points}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
