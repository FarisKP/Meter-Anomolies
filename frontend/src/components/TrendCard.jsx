import { useMemo, useState } from 'react'

const COLORS = ['#4263eb', '#0f9c87', '#e79a35', '#9a62d7', '#d64b59']
const number = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export function TrendCard({ data, onSelectCustomer }) {
  const [customer, setCustomer] = useState('all')
  const [range, setRange] = useState('90')
  const rows = useMemo(() => filterDailyRows(data.daily, customer, range), [data.daily, customer, range])

  return (
    <section className="dashboard-card trend-card">
      <div className="card-heading">
        <div>
          <p className="card-kicker">Usage analysis</p>
          <h2>Historical usage trend</h2>
          <p>Average usage-index per day · compare customer patterns over time</p>
        </div>
        <div className="trend-filters">
          <label>
            <span>Customer</span>
            <select value={customer} onChange={(event) => setCustomer(event.target.value)} aria-label="Customer trend filter">
              <option value="all">All customers</option>
              {data.customers.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </label>
          <label className="filter-label--screen-reader">
            <span>Trend range</span>
            <select value={range} onChange={(event) => setRange(event.target.value)} aria-label="Trend range">
              <option value="90">90 days</option>
              <option value="365">12 months</option>
              <option value="all">All history</option>
            </select>
          </label>
        </div>
      </div>
      <TrendChart rows={rows} customer={customer} onSelectCustomer={onSelectCustomer} range={range} />
      <div className="chart-legend"><span><i className="legend-key" aria-hidden="true" />Daily average usage-index</span><span>Select a trend line to view customer history</span></div>
    </section>
  )
}

function TrendChart({ rows, customer, onSelectCustomer, range }) {
  if (!rows.length) return <div className="empty-chart">No daily usage data found.</div>

  const byCustomer = new Map()
  for (const row of rows) {
    if (!byCustomer.has(row.customer)) byCustomer.set(row.customer, [])
    byCustomer.get(row.customer).push(row)
  }

  const dates = [...new Set(rows.map((row) => row.date))].sort()
  const dateIndex = new Map(dates.map((date, index) => [date, index]))
  const width = 960
  const height = 260
  const left = 48
  const right = 15
  const top = 13
  const bottom = 30
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const values = rows.map((row) => row.average)
  let min = Math.min(0, ...values)
  let max = Math.max(...values)
  if (max === min) max = min + 1
  const padding = (max - min) * 0.12
  min = Math.max(0, min - padding)
  max += padding
  const x = (date) => left + (dates.length < 2 ? plotWidth / 2 : (dateIndex.get(date) / (dates.length - 1)) * plotWidth)
  const y = (value) => top + ((max - value) / (max - min)) * plotHeight

  return (
    <div className="trend-chart-scroll">
      <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily average usage trend">
        {[0, 1, 2, 3, 4].map((index) => {
          const value = min + ((max - min) * index) / 4
          const position = y(value)
          return <g key={index}><line className="chart-gridline" x1={left} y1={position} x2={width - right} y2={position} /><text x={left - 8} y={position + 3} textAnchor="end">{number.format(value)}</text></g>
        })}
        <line className="chart-axis" x1={left} y1={top + plotHeight} x2={width - right} y2={top + plotHeight} />
        {[...byCustomer].map(([id, series], index) => {
          const sortedSeries = [...series].sort((a, b) => a.date.localeCompare(b.date))
          const color = COLORS[index % COLORS.length]
          const points = sortedSeries.map((row) => `${x(row.date)},${y(row.average)}`).join(' ')
          const last = sortedSeries.at(-1)
          return (
            <g key={id}>
              <polyline className="trend-line trend-line--interactive" stroke={color} points={points} role="button" tabIndex="0" aria-label={`View ${id} customer history`} onClick={() => onSelectCustomer(id, range === 'all' ? null : Number(range))} onKeyDown={(event) => activateOnKey(event, () => onSelectCustomer(id, range === 'all' ? null : Number(range)))}><title>{`View ${id} customer history`}</title></polyline>
              {customer !== 'all' && last && <circle cx={x(last.date)} cy={y(last.average)} r="3.5" fill={color}><title>{`${id}: ${number.format(last.average)}`}</title></circle>}
            </g>
          )
        })}
        <text x={left} y={height - 6}>{dates[0]}</text>
        <text x={width - right} y={height - 6} textAnchor="end">{dates.at(-1)}</text>
      </svg>
    </div>
  )
}

function activateOnKey(event, callback) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    callback()
  }
}

function filterDailyRows(daily, customer, range) {
  let rows = daily.filter((row) => customer === 'all' || row.customer === customer)
  if (range === 'all') return rows

  const latest = Math.max(...daily.map((row) => Date.parse(`${row.date}T00:00:00`)))
  const minimum = latest - Number(range) * 86_400_000
  rows = rows.filter((row) => Date.parse(`${row.date}T00:00:00`) >= minimum)
  return rows
}
