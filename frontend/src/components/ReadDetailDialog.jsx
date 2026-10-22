import { useEffect, useRef } from 'react'
import { CustomerLink } from './CustomerLink.jsx'

const decimal = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function ReadDetailDialog({ row, onClose, onViewCustomer }) {
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = dialogRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.body.classList.add('dialog-open')
    document.addEventListener('keydown', handleKeyDown)
    closeButtonRef.current?.focus()
    return () => {
      document.body.classList.remove('dialog-open')
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused instanceof HTMLElement && previouslyFocused.focus()
    }
  }, [onClose])

  const result = readResult(row.flag)
  const fields = [
    ['Customer', <CustomerLink customer={row['cust-id']} onSelectCustomer={onViewCustomer} />],
    ['Budget indicator', row['budget indicator'] || '—'],
    ['Meter', row['meter-num'] || '—'],
    ['Read timestamp', row['current-meter-read-timestamp'] || '—'],
    ['Current meter read', row['current-meter-read'] || '—'],
    ['Previous meter read', row['previous-meter-read'] || '—'],
    ['Usage index', decimal.format(Number(row.usageNumber))],
    ['Historical baseline mean', row.baselineMean ? decimal.format(Number(row.baselineMean)) : 'Not available'],
    ['Spike threshold', row.threshold ? decimal.format(Number(row.threshold)) : 'Not available'],
  ]

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="read-detail-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="read-detail-title" aria-describedby="read-detail-description">
        <header className="dialog-header">
          <div>
            <p className="card-kicker">Meter read details</p>
            <h2 id="read-detail-title">{row['cust-id']} · meter read details</h2>
            <p id="read-detail-description">{row['current-meter-read-timestamp']}</p>
          </div>
          <button className="dialog-close" ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close meter read details">×</button>
        </header>
        <div className="read-result-summary">
          <span className={`result-badge result-badge--${result.tone}`}>{result.label}</span>
          <p>{row.reason || 'No matching analysis result found.'}</p>
        </div>
        <dl className="read-detail-list">
          {fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
      </section>
    </div>
  )
}

function readResult(flag) {
  if (flag === 'TRUE') return { label: 'SPIKE', tone: 'alert' }
  if (flag === 'FALSE') return { label: 'WITHIN RANGE', tone: 'clear' }
  if (flag === 'INSUFFICIENT_HISTORY') return { label: 'INSUFFICIENT HISTORY', tone: 'unknown' }
  return { label: 'NOT ANALYZED', tone: 'unknown' }
}
