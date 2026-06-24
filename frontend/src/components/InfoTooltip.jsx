import styles from './InfoTooltip.module.css'

export default function InfoTooltip({ children, label = 'About this page' }) {
  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={styles.trigger}
        aria-label={label}
        onClick={(e) => e.preventDefault()}
      >
        i
      </button>
      <span className={styles.bubble} role="tooltip">
        {children}
      </span>
    </span>
  )
}
