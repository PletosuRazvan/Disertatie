import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useForecast } from '../context/ForecastContext'
import styles from './Navbar.module.css'

export default function Navbar() {
  const { user, logout, isLoggedIn } = useAuth()
  const { loading: forecasting } = useForecast()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <nav className={styles.nav}>
      <Link to="/" className={styles.brand}>
        <span className={styles.logo}>⚽</span>
        <span>EPL<strong>Predict</strong></span>
      </Link>

      <div className={styles.links}>
        <NavLink to="/"            className={({ isActive }) => isActive ? styles.active : ''}>Home</NavLink>
        <NavLink to="/standings"   className={({ isActive }) => isActive ? styles.active : ''}>Standings</NavLink>
        <NavLink to="/results"     className={({ isActive }) => isActive ? styles.active : ''}>Results</NavLink>
        <NavLink to="/predictions" className={({ isActive }) => isActive ? styles.active : ''}>Predictions</NavLink>
        <NavLink to="/simulator"   className={({ isActive }) => isActive ? styles.active : ''}>Simulator</NavLink>
        <NavLink to="/forecast"    className={({ isActive }) => isActive ? styles.active : ''}>
          Forecast
          {forecasting && <span className={styles.runningDot} title="Forecast running…" />}
        </NavLink>
        {isLoggedIn && (
          <NavLink to="/history"   className={({ isActive }) => isActive ? styles.active : ''}>History</NavLink>
        )}
        <NavLink to="/about"       className={({ isActive }) => isActive ? styles.active : ''}>About</NavLink>
      </div>

      <div className={styles.auth}>
        {isLoggedIn ? (
          <>
            <span className={styles.username}>{user.name}</span>
            <button className="btn btn-outline" onClick={handleLogout}>Logout</button>
          </>
        ) : (
          <>
            <Link to="/login"    className="btn btn-outline">Login</Link>
            <Link to="/register" className="btn btn-primary">Sign Up</Link>
          </>
        )}
      </div>
    </nav>
  )
}
