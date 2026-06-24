import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useForecast } from '../context/ForecastContext'
import styles from './Navbar.module.css'

export default function Navbar() {
  const { user, logout, isLoggedIn } = useAuth()
  const { loading: forecasting } = useForecast()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  function handleLogout() {
    logout()
    setOpen(false)
    navigate('/')
  }

  const closeMenu = () => setOpen(false)
  const linkClass = ({ isActive }) => (isActive ? styles.active : '')

  return (
    <nav className={styles.nav}>
      <Link to="/" className={styles.brand} onClick={closeMenu}>
        <span className={styles.logo}>⚽</span>
        <span>EPL<strong>Predict</strong></span>
      </Link>

      <button
        type="button"
        className={`${styles.burger} ${open ? styles.burgerOpen : ''}`}
        aria-label="Toggle navigation menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span /><span /><span />
      </button>

      <div className={`${styles.menu} ${open ? styles.menuOpen : ''}`}>
        <div className={styles.links}>
          <NavLink to="/"            className={linkClass} onClick={closeMenu}>Home</NavLink>
          <NavLink to="/standings"   className={linkClass} onClick={closeMenu}>Standings</NavLink>
          <NavLink to="/results"     className={linkClass} onClick={closeMenu}>Results</NavLink>
          <NavLink to="/predictions" className={linkClass} onClick={closeMenu}>Predictions</NavLink>
          <NavLink to="/simulator"   className={linkClass} onClick={closeMenu}>Simulator</NavLink>
          <NavLink to="/forecast"    className={linkClass} onClick={closeMenu}>
            Forecast
            {forecasting && <span className={styles.runningDot} title="Forecast running…" />}
          </NavLink>
          {isLoggedIn && (
            <NavLink to="/history"   className={linkClass} onClick={closeMenu}>History</NavLink>
          )}
          <NavLink to="/about"       className={linkClass} onClick={closeMenu}>About</NavLink>
        </div>

        <div className={styles.auth}>
          {isLoggedIn ? (
            <>
              <span className={styles.username}>{user.name}</span>
              <button className="btn btn-outline" onClick={handleLogout}>Logout</button>
            </>
          ) : (
            <>
              <Link to="/login"    className="btn btn-outline" onClick={closeMenu}>Login</Link>
              <Link to="/register" className="btn btn-primary" onClick={closeMenu}>Sign Up</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
