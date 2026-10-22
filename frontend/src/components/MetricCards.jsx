const formatNumber = new Intl.NumberFormat()

export function MetricCards({ data, onOpenDetails }) {
  const queuedCount = data.inputFeedSpikeCandidateCount || 0
  const screenedCount = data.screenedReadCount ?? data.currentCount
  const screenedLatest = data.screenedLatest || data.latest
  const budgetFlagged = data.budgetFlaggedCount ?? data.current.filter(
    (row) => row.flag === 'TRUE' && row['budget indicator'] === 'Y',
  ).length

  const cards = [
    { key: 'history', label: 'Historical readings', value: formatNumber.format(data.historyCount), note: `${data.historyStart} through ${data.historyEnd}`, tone: 'blue' },
    { key: 'customers', label: 'Customers monitored', value: formatNumber.format(data.customers.length), note: 'One meter per customer in this dataset', tone: 'teal' },
    { key: 'current', detailType: 'screened', label: 'Current reads screened', value: formatNumber.format(screenedCount), note: `Latest: ${screenedLatest || 'No current reads'}${queuedCount ? ` | ${queuedCount} pending review` : ''}`, tone: 'violet' },
    { key: 'flags', detailType: 'screened-flags', label: 'Usage spike flags', value: formatNumber.format(data.flaggedCount), note: queuedCount ? `${queuedCount} pending investigation; not a customer finding` : 'For review; not a customer finding', tone: 'red', alert: data.flaggedCount > 0 },
    { key: 'budget-flags', detailType: 'screened-budget-flags', label: 'Budget customer spike flags', value: formatNumber.format(budgetFlagged), note: 'Flagged reads for budget indicator Y', tone: 'red', alert: budgetFlagged > 0 },
    { key: 'missing', label: 'Missing read gaps', value: formatNumber.format(data.missingReadGapCount), note: `${data.missingReadCount} fully missing month(s), if any`, tone: 'amber', alert: data.missingReadGapCount > 0 },
  ]

  return (
    <section className="metric-grid" aria-label="Meter usage summary">
      {cards.map((card) => (
        <button
          type="button"
          className={`metric-card metric-card--interactive metric-card--${card.tone}${card.alert ? ' metric-card--alert' : ''}`}
          key={card.key}
          onClick={() => onOpenDetails({ type: card.detailType || card.key })}
          aria-label={`View ${card.label.toLowerCase()} details`}
        >
          <span className="metric-card__label">{card.label}</span>
          <strong className="metric-card__value">{card.value}</strong>
          <span className="metric-card__note">{card.note}</span>
        </button>
      ))}
    </section>
  )
}
