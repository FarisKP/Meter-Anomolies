import { useEffect, useMemo, useRef, useState } from 'react'
import { getHourlyData } from '../api/dashboard.js'

const number = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export function CustomerHistoryDialog({ customer, initialDays, onClose }) {
  const [range, setRange] = useState(initialDays === null ? 'all' : String(initialDays))
  const [requestVersion, setRequestVersion] = useState(0)
  const [state, setState] = useState({ status: 'loading', rows: [], error: null })
  const [selectedDate, setSelectedDate] = useState(null)
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)
  const daily = useMemo(() => toDailyTotals(state.rows), [state.rows])

  useEffect(() => {
    const controller = new AbortController()
    const days = range === 'all' ? null : Number(range)
    setSelectedDate(null)
    setState({ status: 'loading', rows: [], error: null })

    getHourlyData(customer, days, { signal: controller.signal })
      .then((response) => setState({ status: 'ready', rows: response.data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setState({ status: 'error', rows: [], error })
      })

    return () => controller.abort()
  }, [customer, range, requestVersion])

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

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="customer-history-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="customer-history-title">
        <header className="dialog-header">
          <div>
            <p className="card-kicker">Customer history</p>
            <h2 id="customer-history-title">Usage detail · {customer}</h2>
            <p>Daily usage totals, calculated from the recorded four-hour meter readings.</p>
          </div>
          <button className="dialog-close" ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close customer history">×</button>
        </header>
        <div className="history-controls">
          <label><span>History range</span><select value={range} onChange={(event) => setRange(event.target.value)}><option value="90">90 days</option><option value="365">12 months</option><option value="all">All history</option></select></label>
        </div>
        {state.status === 'loading' && <div className="history-loading" aria-live="polite">Loading recorded readings…</div>}
        {state.status === 'error' && <div className="history-error" role="alert"><p>Could not load customer history: {state.error.message}</p><button type="button" className="retry-button" onClick={() => setRequestVersion((value) => value + 1)}>Try again</button></div>}
        {state.status === 'ready' && <CustomerHistoryContent daily={daily} rows={state.rows} selectedDate={selectedDate} onSelectDate={setSelectedDate} />}
      </section>
    </div>
  )
}

function CustomerHistoryContent({ daily, rows, selectedDate, onSelectDate }) {
  if (!daily.length) return <div className="history-loading">No readings in this selection.</div>

  const total = daily.reduce((sum, row) => sum + row.total, 0)
  const highest = daily.reduce((current, row) => row.total > current.total ? row : current, daily[0])
  return (
    <>
      <section className="history-stat-grid" aria-label="Customer history summary">
        <article><span>Dates</span><strong>{daily.length.toLocaleString()}</strong></article>
        <article><span>Recorded reads</span><strong>{rows.length.toLocaleString()}</strong></article>
        <article><span>Mean daily total</span><strong>{number.format(total / daily.length)}</strong></article>
        <article><span>Highest daily total</span><strong>{number.format(highest.total)}</strong><small>{highest.date}</small></article>
      </section>
      <DailyTotalChart daily={daily} onSelectDate={onSelectDate} />
      {selectedDate && <FourHourReadings rows={rows} date={selectedDate} />}
      <div className="history-table-wrap">
        <table className="data-table history-table">
          <thead><tr><th>Date</th><th>Daily usage total</th><th>Recorded reads</th></tr></thead>
          <tbody>{[...daily].reverse().map((row) => <tr key={row.date}><td>{row.date}</td><td><strong>{number.format(row.total)}</strong></td><td>{row.count}</td></tr>)}</tbody>
        </table>
      </div>
    </>
  )
}

function DailyTotalChart({ daily, onSelectDate }) {
  const width = 980
  const height = 300
  const left = 56
  const right = 18
  const top = 18
  const bottom = 42
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const max = Math.max(...daily.map((row) => row.total), 1) * 1.12
  const x = (index) => left + (daily.length < 2 ? plotWidth / 2 : (index / (daily.length - 1)) * plotWidth)
  const y = (value) => top + ((max - value) / max) * plotHeight
  const points = daily.map((row, index) => `${x(index)},${y(row.total)}`).join(' ')
  const labelIndexes = [...new Set([0, Math.floor((daily.length - 1) / 2), daily.length - 1])]

  return (
    <div className="customer-history-chart-scroll">
      <svg className="customer-history-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily meter usage totals">
        {[0, 1, 2, 3, 4, 5].map((index) => {
          const value = (max * index) / 5
          const position = y(value)
          return <g key={index}><line className="chart-gridline" x1={left} y1={position} x2={width - right} y2={position} /><text x={left - 8} y={position + 3} textAnchor="end">{number.format(value)}</text></g>
        })}
        <line className="chart-axis" x1={left} y1={top + plotHeight} x2={width - right} y2={top + plotHeight} />
        <polyline className="customer-history-line" points={points} />
        {daily.map((row, index) => <circle key={row.date} className="customer-history-point customer-history-point--interactive" cx={x(index)} cy={y(row.total)} r={daily.length > 500 ? 2 : 3} tabIndex="0" role="button" aria-label={`View four-hour readings for ${row.date}`} onClick={() => onSelectDate(row.date)} onKeyDown={(event) => activateOnKey(event, () => onSelectDate(row.date))}><title>{`${row.date}: ${number.format(row.total)} daily usage total. Select for four-hour readings.`}</title></circle>)}
        {labelIndexes.map((index) => <text key={index} x={x(index)} y={height - 13} textAnchor={index === 0 ? 'start' : index === daily.length - 1 ? 'end' : 'middle'}>{daily[index].date}</text>)}
      </svg>
    </div>
  )
}

function FourHourReadings({ rows, date }) {
  const dayRows = rows.filter((row) => row.timestamp.slice(0, 10) === date).sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  const slots = [...new Set(dayRows.map((row) => row.timestamp.slice(11, 16)))].sort()
  const width = 980
  const height = 280
  const left = 56
  const right = 18
  const top = 18
  const bottom = 42
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const max = Math.max(...dayRows.map((row) => Number(row.usage)), 1) * 1.12
  const groupWidth = plotWidth / Math.max(slots.length, 1)
  const barWidth = Math.min(54, groupWidth * 0.56)
  const y = (value) => top + ((max - value) / max) * plotHeight

  return (
    <section className="four-hour-detail" aria-labelledby="four-hour-title">
      <div className="four-hour-detail__heading"><div><p className="card-kicker">Selected date</p><h3 id="four-hour-title">Four-hour readings · {date}</h3><p>Usage-index at each recorded meter interval.</p></div></div>
      <div className="customer-history-chart-scroll">
        <svg className="customer-history-chart four-hour-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Four-hour meter readings for ${date}`}>
          {[0, 1, 2, 3, 4].map((index) => {
            const value = (max * index) / 4
            const position = y(value)
            return <g key={index}><line className="chart-gridline" x1={left} y1={position} x2={width - right} y2={position} /><text x={left - 8} y={position + 3} textAnchor="end">{number.format(value)}</text></g>
          })}
          <line className="chart-axis" x1={left} y1={top + plotHeight} x2={width - right} y2={top + plotHeight} />
          {dayRows.map((row, index) => {
            const center = left + (index + 0.5) * groupWidth
            const topY = y(Number(row.usage))
            return <g key={row.timestamp}><rect className="four-hour-bar" x={center - barWidth / 2} y={topY} width={barWidth} height={top + plotHeight - topY} rx="4"><title>{`${row.timestamp}: ${number.format(Number(row.usage))} usage-index`}</title></rect><text x={center} y={height - 14} textAnchor="middle">{row.timestamp.slice(11, 16)}</text></g>
          })}
        </svg>
      </div>
      <div className="history-table-wrap four-hour-table-wrap"><table className="data-table history-table" aria-label={`Four-hour meter readings for ${date}`}><thead><tr><th>Date</th><th>Time slot</th><th>Usage index</th></tr></thead><tbody>{dayRows.map((row) => <tr key={row.timestamp}><td>{date}</td><td>{row.timestamp.slice(11, 16)}</td><td><strong>{number.format(Number(row.usage))}</strong></td></tr>)}</tbody></table></div>
    </section>
  )
}

function activateOnKey(event, callback) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    callback()
  }
}

function toDailyTotals(rows) {
  const byDate = new Map()
  for (const row of rows) {
    const date = row.timestamp.slice(0, 10)
    const current = byDate.get(date) || { date, total: 0, count: 0 }
    current.total += Number(row.usage)
    current.count += 1
    byDate.set(date, current)
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
}
