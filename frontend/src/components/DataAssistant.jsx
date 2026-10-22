import { useEffect, useRef, useState } from 'react'

const number = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const suggestions = [
  'Which reads were flagged?',
  'Show CUST0003 history',
  'What is the recent trend?',
  'What is the highest historical usage?',
]

export function DataAssistant({ data, backend, isOpen, onClose, onViewCustomer }) {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const inputRef = useRef(null)
  const messagesRef = useRef(null)
  const drawerRef = useRef(null)
  const closeButtonRef = useRef(null)

  useEffect(() => {
    if (!data || messages.length) return
    const source = backend === 'supabase' ? 'Supabase' : 'CSV'
    setMessages([{ role: 'bot', text: `Hi. I can answer questions about historical usage, current reads, spike flags, and recent trends in the loaded ${source} data.` }])
  }, [backend, data, messages.length])

  useEffect(() => {
    if (!isOpen) return undefined
    const previouslyFocused = document.activeElement
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = drawerRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
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
    document.body.classList.add('assistant-open')
    document.addEventListener('keydown', handleKeyDown)
    window.setTimeout(() => closeButtonRef.current?.focus(), 180)
    return () => {
      document.body.classList.remove('assistant-open')
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused instanceof HTMLElement && previouslyFocused.focus()
    }
  }, [isOpen, onClose])

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const submitQuestion = (event) => {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || !data) return
    setMessages((items) => [...items, { role: 'user', text: trimmed }, { role: 'bot', text: answerQuestion(trimmed, data) }])
    setQuestion('')
  }

  const chooseSuggestion = (text) => {
    setMessages((items) => [...items, { role: 'user', text }, { role: 'bot', text: answerQuestion(text, data) }])
    setQuestion('')
  }

  if (!isOpen) return null

  return (
    <>
      <div className="assistant-backdrop assistant-backdrop--open" onMouseDown={onClose} aria-hidden="true" />
      <aside className="assistant-drawer assistant-drawer--open" ref={drawerRef} id="data-assistant" role="dialog" aria-modal="true" aria-labelledby="data-assistant-title">
        <header className="assistant-header">
          <div className="assistant-icon" aria-hidden="true">AI</div>
          <div><h2 id="data-assistant-title">Usage data assistant</h2><p>Answers grounded in the loaded meter history</p></div>
          <button className="assistant-close" ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close data assistant">×</button>
        </header>
        <p className="assistant-scope">Data scope: historical and current meter reads plus spike-analysis results from {backend === 'supabase' ? 'Supabase' : 'CSV'}. The assistant summarizes this data; it does not infer causes for usage changes.</p>
        <div className="assistant-messages" ref={messagesRef} aria-live="polite">
          {messages.map((message, index) => <AssistantMessage data={data} key={`${message.role}-${index}`} message={message} onViewCustomer={onViewCustomer} />)}
        </div>
        <div className="assistant-suggestions">
          {suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => chooseSuggestion(suggestion)}>{suggestion}</button>)}
        </div>
        <form className="assistant-form" onSubmit={submitQuestion}>
          <input ref={inputRef} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about a customer or usage…" autoComplete="off" />
          <button type="submit">Ask</button>
        </form>
        <p className="assistant-footnote"><strong>Data assistant.</strong> Uses data-grounded question patterns locally; no external AI service or customer data sharing.</p>
      </aside>
    </>
  )
}

function AssistantMessage({ data, message, onViewCustomer }) {
  const customerPattern = new RegExp(`(${data.customers.map(escapeRegExp).join('|')})`, 'g')
  const parts = message.text.split(customerPattern)
  return (
    <p className={`assistant-message assistant-message--${message.role}`}>
      {parts.map((part, index) => data.customers.includes(part)
        ? <button className="assistant-customer-link" type="button" key={`${part}-${index}`} onClick={() => onViewCustomer(part)}>{part}</button>
        : part)}
    </p>
  )
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function answerQuestion(question, data) {
  const query = question.toLowerCase()
  const customer = data.customers.find((id) => query.includes(id.toLowerCase()))
  const flags = data.current.filter((row) => row.flag === 'TRUE')

  if (/\b(flag|spike|anomal|alert)\w*\b/.test(query)) {
    if (!flags.length) return data.current.some((row) => row.flag === 'NOT_ANALYZED')
      ? 'No spike flags are available yet because current reads have not been analyzed.'
      : 'No current reads are flagged in the loaded analysis results.'
    return `Flagged current reads:\n${flags.map((row) => `${row['cust-id']} at ${row['current-meter-read-timestamp']}: usage-index ${format(row.usageNumber)}, threshold ${format(row.threshold)}. ${row.reason}`).join('\n')}`
  }

  if (/\b(highest|maximum|max|largest)\b/.test(query)) {
    const candidates = customer ? [customer] : data.customers
    const best = candidates
      .map((id) => ({ customer: id, ...data.customerStats[id].maxAt }))
      .filter((item) => item.date)
      .sort((a, b) => b.usage - a.usage)[0]
    return best ? `Highest historical usage-index ${customer ? `for ${customer}` : 'across the dataset'} was ${format(best.usage)} for ${best.customer} at ${best.date} ${best.time}.` : 'No historical usage value was found.'
  }

  if (/\b(trend|increas|decreas|changed|change)\w*\b/.test(query)) {
    return customer ? trendFor(customer, data) : `Select a customer to review its recent 30-day trend. ${flags.length ? `${flags.length} current read(s) are flagged.` : 'There are no flagged current reads in the loaded results.'}`
  }

  if (customer) {
    const stats = data.customerStats[customer]
    const currentRows = data.current.filter((row) => row['cust-id'] === customer)
    if (/\b(current|latest|new|today|read)\w*\b/.test(query) && currentRows.length) {
      return currentRows.map((row) => `${customer} latest read: usage-index ${format(row.usageNumber)} at ${row['current-meter-read-timestamp']}; status ${row.flag}${row.threshold ? `, threshold ${format(row.threshold)}` : ''}.`).join('\n')
    }
    return `${customer} has ${stats.readings.toLocaleString()} historical readings over ${stats.days.toLocaleString()} days. Mean usage-index: ${format(stats.mean)}; mean daily average: ${format(stats.dailyAverage)}; 99th percentile: ${format(stats.p99)}; maximum: ${format(stats.max)}${stats.maxAt ? ` on ${stats.maxAt.date} at ${stats.maxAt.time}` : ''}.`
  }

  if (/\b(average|mean|typical|history|historical)\w*\b/.test(query)) {
    return `Across the loaded history, ${data.historyCount.toLocaleString()} readings cover ${data.customers.length} customers from ${data.historyStart} to ${data.historyEnd}. Ask for a customer ID (for example, “average for CUST0003”) to see that customer’s baseline statistics.`
  }

  return 'I can summarize the loaded meter data. Try asking which reads were flagged, a customer’s historical average, that customer’s recent trend, or the highest historical usage. I only report values present in the loaded data.'
}

function trendFor(customer, data) {
  const rows = data.daily.filter((row) => row.customer === customer).sort((a, b) => a.date.localeCompare(b.date))
  if (rows.length < 2) return 'There is not enough daily history to calculate a trend.'
  const latest = rows.slice(-30)
  const previous = rows.slice(-60, -30)
  if (!previous.length) return 'There are fewer than 60 daily records, so I cannot compare the latest 30 days with the prior 30 days.'
  const average = (items) => items.reduce((sum, row) => sum + row.average, 0) / items.length
  const previousAverage = average(previous)
  const currentAverage = average(latest)
  const percent = previousAverage ? ((currentAverage - previousAverage) / previousAverage) * 100 : 0
  const direction = percent > 2 ? 'increased' : percent < -2 ? 'decreased' : 'was broadly steady'
  return `For ${customer}, mean daily usage-index was ${format(previousAverage)} in the prior 30-day period and ${format(currentAverage)} in the latest 30 days (through ${latest.at(-1).date}). It ${direction} by ${format(Math.abs(percent), 1)}%.`
}

function format(value, digits = 2) {
  return new Intl.NumberFormat(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value || 0))
}
