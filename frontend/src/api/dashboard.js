const API_ROOT = '/api'

/**
 * @typedef {{ customer: string, timestamp: string, usage: number }} HourlyReading
 * @typedef {{ date: string, average: number, total: number, count: number, customer: string }} DailyUsage
 * @typedef {{ customer: string, month: string, monthLabel: string }} MissingReadMonth
 * @typedef {{ customer: string, start: string, end: string, missingReads: number }} MissingReadGap
 * @typedef {{
 *   historyCount: number,
 *   currentCount: number,
 *   screenedReadCount: number,
 *   screenedLatest: string,
 *   latest: string,
 *   customers: string[],
 *   customerStats: Record<string, object>,
 *   daily: DailyUsage[],
 *   slots: Record<string, object>,
 *   current: object[],
 *   flaggedCount: number,
 *   budgetFlaggedCount: number,
 *   missingReadMonths: MissingReadMonth[],
 *   missingReadCount: number,
 *   missingReadGaps: MissingReadGap[],
 *   missingReadGapCount: number,
 *   historyStart: string,
 *   historyEnd: string
 * }} DashboardData
 */

export class DashboardApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'DashboardApiError'
    this.status = status
  }
}

async function getJson(path, options = {}) {
  const response = await fetch(path, {
    cache: 'no-store',
    signal: options.signal,
  })

  if (!response.ok) {
    throw new DashboardApiError(`Request failed with HTTP ${response.status}.`, response.status)
  }

  return {
    data: await response.json(),
    backend: response.headers.get('X-Data-Backend'),
  }
}

async function sendJson(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new DashboardApiError(data.error || `Request failed with HTTP ${response.status}.`, response.status)
  }
  return data
}

/** @returns {Promise<{ data: DashboardData, backend: string | null }>} */
export function getDashboardData(options) {
  return getJson(`${API_ROOT}/data`, options)
}

/** @returns {Promise<{ data: HourlyReading[], backend: string | null }>} */
export function getHourlyData(customer = 'all', days = 90, options) {
  const params = new URLSearchParams({
    customer,
    days: days === null ? 'all' : String(days),
  })
  return getJson(`${API_ROOT}/hourly?${params}`, options)
}

export function getFeedReference(options) {
  return getJson(`${API_ROOT}/feed-reference`, options)
}

export function submitFeedReading(payload) {
  return sendJson(`${API_ROOT}/feed-submissions`, payload)
}

export function updateInvestigationTicket(ticketId, payload) {
  return sendJson(`${API_ROOT}/tickets/${encodeURIComponent(ticketId)}`, payload)
}
