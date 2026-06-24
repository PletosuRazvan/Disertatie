import styles from './About.module.css'

const STACK = [
  { name: 'React 18 + Vite',   role: 'Single-page frontend with React Router v6',     icon: '⚛️' },
  { name: 'Flask 3',           role: 'REST API backend (Python)',                     icon: '🐍' },
  { name: 'PyTorch',           role: 'Multi-task neural network for predictions',      icon: '🔥' },
  { name: 'MongoDB',           role: 'Datastore for matches, users & predictions',     icon: '🍃' },
  { name: 'JWT',               role: 'Stateless authentication',                       icon: '🔐' },
]

const FEATURES = [
  { text: 'Live league standings with form',                 icon: '📊' },
  { text: 'Full match history, browsable by season',         icon: '📅' },
  { text: 'Single-match outcome & stats predictions',        icon: '🎯' },
  { text: 'Season simulator (one full season)',              icon: '⚽' },
  { text: 'Monte-Carlo forecast (thousands of seasons)',     icon: '🔮' },
  { text: 'User accounts & saved predictions',               icon: '👤' },
]

const STATS = [
  { value: '12.6k', label: 'Matches in dataset' },
  { value: '52%',   label: 'Outcome accuracy' },
  { value: '50',    label: 'Engineered features' },
  { value: '51',    label: 'Teams modelled' },
]

export default function About() {
  return (
    <div className="page-wrapper">
      <h1 className="page-title">About <span>EPLPredict</span></h1>

      <div className={styles.statRow}>
        {STATS.map((s) => (
          <div key={s.label} className={`card ${styles.statCard}`}>
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      <div className={styles.grid}>
        {/* Project description */}
        <section className={`card ${styles.section}`}>
          <h2>Project Overview</h2>
          <p>
            <strong>EPLPredict</strong> is a dissertation project that pairs three decades of
            English Premier League data with a machine-learning model to predict match
            outcomes and simulate entire seasons.
          </p>
          <p style={{ marginTop: '.8rem' }}>
            Browse historical results, follow the standings, get predictions for any fixture,
            and run Monte-Carlo simulations to see how likely each club is to win the title,
            reach the top four, or be relegated.
          </p>
        </section>

        {/* How the model works */}
        <section className={`card ${styles.section}`}>
          <h2>How the Model Works <span className={styles.tag}>PyTorch</span></h2>
          <p>
            A multi-task feed-forward neural network shares one representation across three
            heads, all from <strong>pre-match</strong> inputs only (no data leakage):
          </p>
          <ul className={styles.bullets}>
            <li><strong>Outcome</strong> — home win / draw / away win probabilities</li>
            <li><strong>Goals</strong> — expected goals per side (Poisson)</li>
            <li><strong>Match stats</strong> — corners, cards, shots & more (Poisson)</li>
          </ul>
          <p style={{ marginTop: '.8rem' }}>
            Each club has learned <strong>home & away embeddings</strong>, and recent seasons are
            weighted more heavily so the model reflects current form.
          </p>
        </section>

        {/* Features */}
        <section className={`card ${styles.section}`}>
          <h2>What You Can Do</h2>
          <div className={styles.featureList}>
            {FEATURES.map((f) => (
              <div key={f.text} className={styles.featureItem}>
                <span className={styles.featureIcon}>{f.icon}</span>
                <span>{f.text}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Tech stack */}
        <section className={`card ${styles.section}`}>
          <h2>Tech Stack</h2>
          <div className={styles.stackList}>
            {STACK.map((s) => (
              <div key={s.name} className={styles.stackItem}>
                <span className={styles.stackIcon}>{s.icon}</span>
                <div>
                  <strong>{s.name}</strong>
                  <p>{s.role}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

