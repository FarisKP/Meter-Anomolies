const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const wholeNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const decimalNumber = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export function SpikeCharts({ data, onOpenDetails, onSelectRead }) {
  return (
    <div className="spike-chart-stack">
      <SpikeChartCard rows={data.current} queuedCandidates={data.inputFeedSpikeCandidates || []} onOpenDetails={onOpenDetails} onSelectRead={onSelectRead} />
      <SpikeChartCard rows={data.current} queuedCandidates={data.inputFeedSpikeCandidates || []} onOpenDetails={onOpenDetails} onSelectRead={onSelectRead} budgetOnly />
    </div>
  )
}

function SpikeChartCard({ rows, queuedCandidates, onOpenDetails, onSelectRead, budgetOnly = false }) {
  const spikes = buildSpikes(rows, budgetOnly)
  const title = budgetOnly ? 'Flagged usage spikes · budget customers' : 'Flagged usage spikes · all customers'
  const description = budgetOnly
    ? 'The same view, filtered to flagged reads with budget indicator Y.'
    : 'Each bar is one flagged read. Its height shows how far usage exceeded its same-slot historical threshold.'

  return (
    <section className="dashboard-card spike-card">
      <div className="card-heading">
        <div>
          <p className="card-kicker">Spike analysis</p>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <span className="spike-count">{spikes.length} flagged read{spikes.length === 1 ? '' : 's'}</span>
      </div>
      {!rows.length && <div className="empty-chart">{queuedCandidates.length ? `${queuedCandidates.length} input-feed candidate${queuedCandidates.length === 1 ? '' : 's'} await${queuedCandidates.length === 1 ? 's' : ''} associate review in the protected queue.` : 'No current readings. Add rows to the current usage CSV and run the analysis script.'}</div>}
      {rows.length > 0 && spikes.length === 0 && <div className="empty-chart">No flagged reads in this view.</div>}
      {spikes.length > 0 && <SpikeChart spikes={spikes} budgetOnly={budgetOnly} onOpenDetails={onOpenDetails} onSelectRead={(spike) => onSelectRead(rows[spike.index])} />}
      {spikes.length > 0 && <div className="chart-legend"><span><i className="legend-key legend-key--red" aria-hidden="true" />One bar = one flagged read</span><span>Bar height = percentage above historical threshold</span></div>}
    </section>
  )
}

function SpikeChart({ spikes, budgetOnly, onOpenDetails, onSelectRead }) {
  const maxValue = Math.max(...spikes.map((spike) => spike.spikePercent))
  const rawStep = Math.max(100, maxValue / 4)
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10) * magnitude
  const axisMax = Math.max(step * 3, Math.ceil(maxValue / step) * step)
  const width = 960
  const height = 300
  const left = 72
  const right = 18
  const top = 36
  const bottom = 48
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const monthWidth = plotWidth / 12
  const y = (value) => top + plotHeight - (value / axisMax) * plotHeight
  const ticks = Array.from({ length: Math.round(axisMax / step) + 1 }, (_, index) => index * step)

  return (
    <div className="spike-chart-scroll">
      <svg className="spike-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Flagged usage spikes by month. Bar height is the percentage above the historical threshold.">
        <text className="spike-axis-title" x={left} y="16">SPIKE % ABOVE HISTORICAL THRESHOLD</text>
        {ticks.map((tick) => {
          const position = y(tick)
          const upperBound = Math.min(axisMax, tick + step)
          return <g key={tick}><line className="chart-gridline" x1={left} y1={position} x2={width - right} y2={position} /><text className="spike-range-label" x={left - 9} y={position + 3} textAnchor="end" tabIndex="0" role="button" aria-label={`View flagged reads from ${wholeNumber.format(tick)}% to ${wholeNumber.format(upperBound)}% above threshold`} onClick={() => onOpenDetails({ type: 'spike-range', low: tick, high: upperBound, budgetOnly })} onKeyDown={(event) => activateOnKey(event, () => onOpenDetails({ type: 'spike-range', low: tick, high: upperBound, budgetOnly }))}>{wholeNumber.format(tick)}%</text></g>
        })}
        <line className="chart-axis" x1={left} y1={top + plotHeight} x2={width - right} y2={top + plotHeight} />
        {MONTHS.map((month, index) => <text className="spike-month-label" key={month} x={left + (index + 0.5) * monthWidth} y={height - 17} textAnchor="middle" tabIndex="0" role="button" aria-label={`View ${month} flagged reads`} onClick={() => onOpenDetails({ type: 'spike-month', month: index + 1, budgetOnly })} onKeyDown={(event) => activateOnKey(event, () => onOpenDetails({ type: 'spike-month', month: index + 1, budgetOnly }))}>{month}</text>)}
        {MONTHS.flatMap((_, monthIndex) => {
          const group = spikes.filter((spike) => spike.month === monthIndex + 1)
          const barWidth = Math.min(30, (monthWidth * 0.55) / Math.max(group.length, 1))
          return group.map((spike, index) => {
            const center = left + (monthIndex + 0.5) * monthWidth + (index - (group.length - 1) / 2) * (barWidth + 6)
            const barY = y(spike.spikePercent)
            const height = top + plotHeight - barY
            const labelY = Math.max(top + 13, barY - 7)
            const label = `${spike.customer} · ${MONTHS[monthIndex]} ${spike.date}: ${decimalNumber.format(spike.spikePercent)}% above threshold; usage ${decimalNumber.format(spike.usage)}`
            return (
              <g key={`${spike.index}-${spike.date}`}>
                <rect className="spike-bar" x={center - barWidth / 2} y={barY} width={barWidth} height={height} rx="5" tabIndex="0" role="button" aria-label={`View details for ${label}`} onClick={() => onSelectRead(spike)} onKeyDown={(event) => activateOnKey(event, () => onSelectRead(spike))}><title>{label}</title></rect>
                <text className="spike-value" x={center} y={labelY} textAnchor="middle">{wholeNumber.format(spike.spikePercent)}%</text>
              </g>
            )
          })
        })}
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

function buildSpikes(rows, budgetOnly) {
  return rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => row.flag === 'TRUE' && Number(row.threshold) > 0 && (!budgetOnly || row['budget indicator'] === 'Y'))
    .map(({ row, index }) => {
      const date = (row['current-meter-read-timestamp'] || '').slice(0, 10)
      const threshold = Number(row.threshold)
      const usage = Number(row.usageNumber)
      return {
        index,
        customer: row['cust-id'],
        date,
        month: Number(date.slice(5, 7)),
        usage,
        spikePercent: Math.max(0, ((usage - threshold) / threshold) * 100),
      }
    })
}
