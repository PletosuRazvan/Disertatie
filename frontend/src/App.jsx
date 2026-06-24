import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ForecastProvider } from './context/ForecastContext'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Predictions from './pages/Predictions'
import Simulator from './pages/Simulator'
import Forecast from './pages/Forecast'
import Results from './pages/Results'
import Standings from './pages/Standings'
import History from './pages/History'
import About from './pages/About'

export default function App() {
  return (
    <AuthProvider>
      <ForecastProvider>
        <Navbar />
        <Routes>
          <Route path="/"            element={<Home />} />
          <Route path="/login"       element={<Login />} />
          <Route path="/register"    element={<Register />} />
          <Route path="/predictions" element={<Predictions />} />
          <Route path="/simulator"   element={<Simulator />} />
          <Route path="/forecast"    element={<Forecast />} />
          <Route path="/results"     element={<Results />} />
          <Route path="/standings"   element={<Standings />} />
          <Route path="/history"     element={<History />} />
          <Route path="/about"       element={<About />} />
          <Route path="*"            element={<NotFound />} />
        </Routes>
      </ForecastProvider>
    </AuthProvider>
  )
}

function NotFound() {
  return (
    <div className="page-wrapper" style={{ textAlign: 'center', paddingTop: '8rem' }}>
      <h1 style={{ fontSize: '4rem', color: 'var(--accent)' }}>404</h1>
      <p style={{ color: 'var(--text-muted)', marginTop: '.5rem' }}>Page not found.</p>
    </div>
  )
}
