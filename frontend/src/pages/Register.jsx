import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/api'
import EyeIcon from '../components/EyeIcon'
import styles from './Auth.module.css'

export default function Register() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [showPw, setShowPw] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (form.password !== form.confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/register', { name: form.name, email: form.email, password: form.password })
      // Auto-login after register
      const { data } = await api.post('/auth/login', { email: form.email, password: form.password })
      login({ name: data.name, email: form.email, token: data.token })
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.error || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrapper}>
      <div className={`card ${styles.box}`}>
        <div className={styles.header}>
          <span className={styles.icon}>⚽</span>
          <h1>Create account</h1>
          <p>Join EPLPredict and start predicting</p>
        </div>

        {error && <div className={styles.errorBanner}>{error}</div>}

        <form onSubmit={handleSubmit} autoComplete="off">
          <div className="form-group">
            <label htmlFor="name">Full Name</label>
            <input id="name" name="name" className="form-control" value={form.name} onChange={handleChange} placeholder="John Smith" required />
          </div>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" className="form-control" value={form.email} onChange={handleChange} placeholder="you@example.com" required />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className={styles.pwWrap}>
              <input id="password" name="password" type={showPw ? 'text' : 'password'} className="form-control" value={form.password} onChange={handleChange} placeholder="Min 8 characters" required minLength={8} />
              <button
                type="button"
                className={styles.pwToggle}
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
                title={showPw ? 'Hide password' : 'Show password'}
              >
                <EyeIcon visible={showPw} />
              </button>
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="confirm">Confirm Password</label>
            <div className={styles.pwWrap}>
              <input id="confirm" name="confirm" type={showConfirm ? 'text' : 'password'} className="form-control" value={form.confirm} onChange={handleChange} placeholder="Repeat password" required />
              <button
                type="button"
                className={styles.pwToggle}
                onClick={() => setShowConfirm((v) => !v)}
                aria-label={showConfirm ? 'Hide password' : 'Show password'}
                title={showConfirm ? 'Hide password' : 'Show password'}
              >
                <EyeIcon visible={showConfirm} />
              </button>
            </div>
          </div>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <p className={styles.footer}>
          Already have an account? <Link to="/login">Sign In</Link>
        </p>
      </div>
    </div>
  )
}
