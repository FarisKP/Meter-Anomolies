import { useMemo } from 'react'
import { CustomerLink } from './CustomerLink.jsx'

const decimal = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const wholeNumber = new Intl.NumberFormat()

export function OperationalReadings({ data, onSelectRead, onSelectCustomer, onCreateTicket }) {
  return (
    <>
      <MissingReadsCard gaps={data.missingReadGaps || []} months={data.missingReadMonths || []} onSelectCustomer={onSelectCustomer} />
      <InputFeedSpikeQueue rows={data.inputFeedSpikeCandidates || []} onSelectRead={onSelectRead} onSelectCustomer={onSelectCustomer} onCreateTicket={onCreateTicket} />
      <IncomingReadsTable rows={data.current} onSelectRead={onSelectRead} onSelectCustomer={onSelectCustomer} />
    </>
  )
}

function MissingReadsCard({ gaps, months, onSelectCustomer }) {
  const hasMissingReads = gaps.length > 0 || months.length > 0

  return (
    <section className="dashboard-card missing-reads-card">
      <div className="card-heading">
        <div>
          <p className="card-kicker">Feed quality</p>
          <h2>Missing incoming reads</h2>
          <p>Contiguous gaps in the expected four-hour feed, plus any fully missing months.</p>
        </div>
        <span className={`status-summary${hasMissingReads ? ' status-summary--alert' : ''}`}>{gaps.length} gap{gaps.length === 1 ? '' : 's'} · {months.length} missing month{months.length === 1 ? '' : 's'}</span>
      </div>
      {!hasMissingReads && <div className="empty-chart empty-chart--compact">No missing four-hour reads or fully missing months detected in the current feed window.</div>}
      {gaps.length > 0 && <ReadGapTable gaps={gaps} onSelectCustomer={onSelectCustomer} />}
      {months.length > 0 && <MissingMonthTable months={months} hasGaps={gaps.length > 0} onSelectCustomer={onSelectCustomer} />}
    </section>
  )
}

function ReadGapTable({ gaps, onSelectCustomer }) {
  return (
    <div className="data-table-wrap data-table-wrap--small">
      <table className="data-table" aria-label="Missing incoming read gaps">
        <thead><tr><th>Customer</th><th>First missing slot</th><th>Last missing slot</th><th>Missing reads</th></tr></thead>
        <tbody>{gaps.map((gap) => <tr key={`${gap.customer}-${gap.start}`}><td><CustomerLink customer={gap.customer} onSelectCustomer={onSelectCustomer} /></td><td>{gap.start}</td><td>{gap.end}</td><td>{wholeNumber.format(gap.missingReads)}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

function MissingMonthTable({ months, hasGaps, onSelectCustomer }) {
  return (
    <section className={hasGaps ? 'missing-months-section' : undefined}>
      {hasGaps && <h3 className="table-subheading">Fully missing months</h3>}
      <div className="data-table-wrap data-table-wrap--small">
        <table className="data-table" aria-label="Fully missing customer months">
          <thead><tr><th>Customer</th><th>Month with no reads</th></tr></thead>
          <tbody>{months.map((month) => <tr key={`${month.customer}-${month.month}`}><td><CustomerLink customer={month.customer} onSelectCustomer={onSelectCustomer} /></td><td>{month.monthLabel}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}

function InputFeedSpikeQueue({ rows, onSelectRead, onSelectCustomer, onCreateTicket }) {
  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => String(b['current-meter-read-timestamp']).localeCompare(String(a['current-meter-read-timestamp']))),
    [rows],
  )

  return (
    <section className="dashboard-card input-spike-queue-card">
      <div className="card-heading">
        <div>
          <p className="card-kicker">Investigation intake</p>
          <h2>Input-feed spike candidates</h2>
          <p>Only validated readings that exceed the deterministic same-slot threshold are queued for associate review.</p>
        </div>
        <span className={`status-summary${rows.length ? ' status-summary--alert' : ''}`}>{wholeNumber.format(rows.length)} candidate{rows.length === 1 ? '' : 's'}</span>
      </div>
      {!rows.length && <div className="empty-chart empty-chart--compact">No input-feed readings are currently awaiting spike investigation.</div>}
      {rows.length > 0 && (
        <div className="data-table-wrap data-table-wrap--small">
          <table className="data-table" aria-label="Input-feed spike candidates">
            <thead><tr><th>Customer</th><th>Meter</th><th>Read time</th><th>Usage index</th><th>Spike indicator</th><th>Automatic ticket</th></tr></thead>
            <tbody>{sortedRows.map((row) => <tr className="read-detail-row" tabIndex="0" role="button" key={`${row['meter-num']}-${row['current-meter-read-timestamp']}`} onClick={() => onSelectRead(row)} onKeyDown={(event) => activateOnKey(event, () => onSelectRead(row))}>
              <td onClick={(event) => event.stopPropagation()}><CustomerLink customer={row['cust-id']} onSelectCustomer={onSelectCustomer} /></td>
              <td>{row['meter-num']}</td>
              <td>{row['current-meter-read-timestamp']}</td>
              <td><strong>{decimal.format(Number(row.usageNumber))}</strong></td>
              <td><span className="result-badge result-badge--alert">SPIKE CANDIDATE</span></td>
              <td><button className="ticket-action" type="button" disabled={!row.investigation?.ticketId} onClick={(event) => { event.stopPropagation(); onCreateTicket(row) }}>{row.investigation?.ticketId ? 'View ticket' : 'Ticket pending'}</button></td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
      <p className="table-footnote">Candidates are copied to the protected <code>meter_reads_temp</code> review queue; this is not a customer notification or a root-cause finding.</p>
    </section>
  )
}

function IncomingReadsTable({ rows, onSelectRead, onSelectCustomer }) {
  const sortedRows = useMemo(() => [...rows].sort((a, b) => Number(b.usageNumber) - Number(a.usageNumber)), [rows])

  return (
    <section className="dashboard-card incoming-reads-card">
      <div className="card-heading">
        <div>
          <p className="card-kicker">Analysis results</p>
          <h2>Incoming meter reads</h2>
          <p>Spike results from the loaded analysis run, ordered by highest usage index.</p>
        </div>
        <span className="status-summary">{wholeNumber.format(rows.length)} reads</span>
      </div>
      {!rows.length && <div className="empty-chart empty-chart--compact">No incoming readings loaded.</div>}
      {rows.length > 0 && (
        <div className="data-table-wrap incoming-reads-table-wrap">
          <table className="data-table incoming-reads-table" aria-label="Incoming meter reads ordered by usage index">
            <thead><tr><th>Customer</th><th>Budget</th><th>Read time</th><th>Usage index</th><th>Historical avg</th><th>Threshold</th><th>Result</th></tr></thead>
            <tbody>
              {sortedRows.map((row, index) => <IncomingReadRow key={`${row['cust-id']}-${row['current-meter-read-timestamp']}-${index}`} row={row} onSelectRead={onSelectRead} onSelectCustomer={onSelectCustomer} />)}
            </tbody>
          </table>
        </div>
      )}
      <p className="table-footnote">A spike flag means the reading exceeded the prototype threshold and needs review.</p>
    </section>
  )
}

function IncomingReadRow({ row, onSelectRead, onSelectCustomer }) {
  const result = formatResult(row.flag)
  return (
    <tr className="read-detail-row" tabIndex="0" role="button" aria-label={`View details for ${row['cust-id']} at ${row['current-meter-read-timestamp']}`} onClick={() => onSelectRead(row)} onKeyDown={(event) => activateOnKey(event, () => onSelectRead(row))}>
      <td onClick={(event) => event.stopPropagation()}><CustomerLink customer={row['cust-id']} onSelectCustomer={onSelectCustomer} /></td>
      <td>{row['budget indicator'] || '—'}</td>
      <td>{row['current-meter-read-timestamp']}</td>
      <td><strong>{decimal.format(Number(row.usageNumber))}</strong></td>
      <td>{row.baselineMean ? decimal.format(Number(row.baselineMean)) : '—'}</td>
      <td>{row.threshold ? decimal.format(Number(row.threshold)) : '—'}</td>
      <td><span className={`result-badge result-badge--${result.tone}`}>{result.label}</span></td>
    </tr>
  )
}

function activateOnKey(event, callback) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    callback()
  }
}

function formatResult(flag) {
  if (flag === 'TRUE') return { label: 'SPIKE', tone: 'alert' }
  if (flag === 'FALSE') return { label: 'WITHIN RANGE', tone: 'clear' }
  if (flag === 'INSUFFICIENT_HISTORY') return { label: 'INSUFFICIENT HISTORY', tone: 'unknown' }
  return { label: 'NOT ANALYZED', tone: 'unknown' }
}
