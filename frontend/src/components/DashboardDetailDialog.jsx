import { useEffect, useMemo, useRef } from 'react'
import { CustomerLink } from './CustomerLink.jsx'

const whole = new Intl.NumberFormat()
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function DashboardDetailDialog({ data, selection, onClose, onSelectCustomer }) {
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)
  const detail = useMemo(() => createDetail(data, selection, onSelectCustomer), [data, selection, onSelectCustomer])

  useEffect(() => {
    const priorFocus = document.activeElement
    const onKeyDown = (event) => {
      if (event.key === 'Escape') return onClose()
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
    document.addEventListener('keydown', onKeyDown)
    closeButtonRef.current?.focus()
    return () => {
      document.body.classList.remove('dialog-open')
      document.removeEventListener('keydown', onKeyDown)
      priorFocus instanceof HTMLElement && priorFocus.focus()
    }
  }, [onClose])

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="dashboard-detail-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="dashboard-detail-title">
        <header className="dialog-header">
          <div><p className="card-kicker">Dashboard details</p><h2 id="dashboard-detail-title">{detail.title}</h2><p>{detail.subtitle}</p></div>
          <button className="dialog-close" ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close dashboard details">×</button>
        </header>
        <div className="dashboard-detail-body">{detail.content}</div>
      </section>
    </div>
  )
}

function createDetail(data, selection, onSelectCustomer) {
  if (selection.type === 'history') {
    const rows = data.customers.map((customer) => {
      const stats = data.customerStats[customer]
      return [<CustomerLink key={customer} customer={customer} onSelectCustomer={onSelectCustomer} />, whole.format(stats.readings), whole.format(stats.days), format(stats.mean), format(stats.p99), format(stats.max), stats.maxAt ? `${stats.maxAt.date} ${stats.maxAt.time}` : '—']
    })
    return makeDetail('Historical reading details', `${whole.format(data.historyCount)} readings from ${data.historyStart} to ${data.historyEnd}`, ['Customer', 'Readings', 'Days', 'Mean usage-index', 'P99', 'Maximum', 'Max timestamp'], rows)
  }
  if (selection.type === 'customers') {
    const rows = data.customers.map((customer) => {
      const stats = data.customerStats[customer]
      return [<CustomerLink key={customer} customer={customer} onSelectCustomer={onSelectCustomer} />, whole.format(stats.days), format(stats.dailyAverage), format(stats.mean), `${whole.format(stats.readings)} readings`]
    })
    return makeDetail('Customer details', `${data.customers.length} customers in the historical file`, ['Customer', 'Historical days', 'Mean daily average', 'Mean reading', 'Data available'], rows)
  }
  if (['screened', 'screened-flags', 'screened-budget-flags'].includes(selection.type)) {
    const isFlagDetail = selection.type !== 'screened'
    const budgetOnly = selection.type === 'screened-budget-flags'
    const screened = [...data.current, ...(data.inputFeedSpikeCandidates || [])]
      .filter((row) => !isFlagDetail || row.flag === 'TRUE')
      .filter((row) => !budgetOnly || row['budget indicator'] === 'Y')
    const rows = screened.map((row) => [
      <CustomerLink key={`${row['cust-id']}-${row['current-meter-read-timestamp']}`} customer={row['cust-id']} onSelectCustomer={onSelectCustomer} />,
      row['budget indicator'] || '-',
      row['meter-num'],
      row['current-meter-read-timestamp'],
      format(row.usageNumber),
      row.baselineMean ? format(row.baselineMean) : '-',
      row.threshold ? format(row.threshold) : '-',
      row.source === 'input_feed_screening' ? 'Pending investigation' : 'Operational feed',
      <ResultBadge key="result" flag={row.flag} />,
    ])
    const title = budgetOnly ? 'Budget customer spike details' : isFlagDetail ? 'Usage spike flag details' : 'Screened meter read details'
    const subtitle = isFlagDetail
      ? `${whole.format(screened.length)} flagged read(s) for review.`
      : `${whole.format(screened.length)} screened read(s), including protected input-feed candidates.`
    return makeDetail(title, subtitle, ['Customer', 'Budget', 'Meter', 'Timestamp', 'Usage index', 'Baseline mean', 'Threshold', 'Disposition', 'Result'], rows)
  }
  if (selection.type === 'current') {
    const rows = data.current.map((row) => [<CustomerLink key={row['cust-id']} customer={row['cust-id']} onSelectCustomer={onSelectCustomer} />, row['budget indicator'] || '—', row['meter-num'], row['current-meter-read-timestamp'], format(row.usageNumber), row.baselineMean ? format(row.baselineMean) : '—', row.threshold ? format(row.threshold) : '—', <ResultBadge key="result" flag={row.flag} />])
    return makeDetail('Current meter read details', `${whole.format(data.currentCount)} incoming readings · latest ${data.latest || 'date unavailable'}`, ['Customer', 'Budget indicator', 'Meter', 'Timestamp', 'Usage index', 'Baseline mean', 'Threshold', 'Result'], rows)
  }
  if (selection.type === 'flags' || selection.type === 'budget-flags') {
    const budgetOnly = selection.type === 'budget-flags'
    const flags = spikeRows(data.current, budgetOnly)
    const rows = flags.map((row) => budgetOnly
      ? [<CustomerLink key={row.customer} customer={row.customer} onSelectCustomer={onSelectCustomer} />, row.timestamp, format(row.usage), row.baseline ? format(row.baseline) : '—', format(row.threshold), `${format(row.spikePercent, 1)}%`, row.reason]
      : [<CustomerLink key={row.customer} customer={row.customer} onSelectCustomer={onSelectCustomer} />, row.timestamp, format(row.usage), row.baseline ? format(row.baseline) : '—', format(row.threshold), row.reason])
    const headers = budgetOnly ? ['Customer', 'Timestamp', 'Usage index', 'Baseline mean', 'Threshold', 'Above threshold', 'Flag reason'] : ['Customer', 'Timestamp', 'Usage index', 'Baseline mean', 'Threshold', 'Flag reason']
    return makeDetail(budgetOnly ? 'Budget customer usage spike details' : 'Usage spike flag details', budgetOnly ? `${flags.length} flagged read(s) for customers with budget indicator Y` : `${flags.length} flagged reading(s) · each flag is for review`, headers, rows)
  }
  if (selection.type === 'missing') {
    const gaps = data.missingReadGaps || []
    const months = data.missingReadMonths || []
    return {
      title: 'Missing incoming reads',
      subtitle: `${gaps.length} gap(s) between expected four-hour reads · ${months.length} fully missing customer-month(s)`,
      content: <><h3 className="detail-section-heading">Read gaps</h3><DetailTable headers={['Customer', 'First missing slot', 'Last missing slot', 'Missing reads']} rows={gaps.map((gap) => [<CustomerLink key={gap.customer} customer={gap.customer} onSelectCustomer={onSelectCustomer} />, gap.start, gap.end, whole.format(gap.missingReads)])} /><h3 className="detail-section-heading">Fully missing months</h3><DetailTable headers={['Customer', 'Missing month', 'Month key']} rows={months.map((month) => [<CustomerLink key={month.customer} customer={month.customer} onSelectCustomer={onSelectCustomer} />, month.monthLabel, month.month])} /></>,
    }
  }
  return spikeDetail(data, selection, onSelectCustomer)
}

function spikeDetail(data, selection, onSelectCustomer) {
  const budgetOnly = selection.budgetOnly
  let rows = spikeRows(data.current, budgetOnly)
  let title
  let subtitle
  if (selection.type === 'spike-month') {
    rows = rows.filter((row) => row.month === selection.month)
    const currentRows = data.current.filter((row) => Number((row['current-meter-read-timestamp'] || '').slice(5, 7)) === selection.month && (!budgetOnly || row['budget indicator'] === 'Y'))
    title = `Spike details · ${MONTHS[selection.month - 1]}${budgetOnly ? ' · budget indicator Y' : ''}`
    subtitle = `${rows.length} flagged customer(s) among ${currentRows.length} current read(s) in this month.`
  } else {
    rows = rows.filter((row) => row.spikePercent >= selection.low && row.spikePercent < selection.high).sort((a, b) => b.spikePercent - a.spikePercent)
    title = `Spike details · percentage band${budgetOnly ? ' · budget indicator Y' : ''}`
    subtitle = `Flagged reads from ${format(selection.low, 0)}% up to ${format(selection.high, 0)}% above their historical threshold.`
  }
  const tableRows = rows.map((row) => [<CustomerLink key={row.customer} customer={row.customer} onSelectCustomer={onSelectCustomer} />, row.timestamp, format(row.usage), row.baseline ? format(row.baseline) : '—', format(row.threshold), `${format(row.spikePercent, 1)}%`])
  return makeDetail(title, subtitle, ['Customer', 'Read timestamp', 'Usage index', 'Baseline mean', 'Threshold', 'Above threshold'], tableRows)
}

function makeDetail(title, subtitle, headers, rows) {
  return { title, subtitle, content: rows.length ? <DetailTable headers={headers} rows={rows} /> : <EmptyDetail>No matching records.</EmptyDetail> }
}

function DetailTable({ headers, rows }) {
  return <div className="detail-table-wrap"><table className="data-table detail-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>
}

function EmptyDetail({ children }) {
  return <div className="empty-chart empty-chart--compact">{children}</div>
}

function ResultBadge({ flag }) {
  const result = flag === 'TRUE' ? ['SPIKE', 'alert'] : flag === 'FALSE' ? ['WITHIN RANGE', 'clear'] : flag === 'INSUFFICIENT_HISTORY' ? ['INSUFFICIENT HISTORY', 'unknown'] : ['NOT ANALYZED', 'unknown']
  return <span className={`result-badge result-badge--${result[1]}`}>{result[0]}</span>
}

function spikeRows(current, budgetOnly) {
  return current.filter((row) => row.flag === 'TRUE' && Number(row.threshold) > 0 && (!budgetOnly || row['budget indicator'] === 'Y')).map((row) => {
    const threshold = Number(row.threshold)
    const usage = Number(row.usageNumber)
    const timestamp = row['current-meter-read-timestamp'] || ''
    return { customer: row['cust-id'], timestamp, month: Number(timestamp.slice(5, 7)), usage, baseline: Number(row.baselineMean), threshold, reason: row.reason, spikePercent: Math.max(0, ((usage - threshold) / threshold) * 100) }
  })
}

function format(value, digits = 2) {
  return new Intl.NumberFormat(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value || 0))
}
