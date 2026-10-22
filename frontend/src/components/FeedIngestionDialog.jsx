import { useEffect, useMemo, useRef, useState } from 'react'
import { getFeedReference, submitFeedReading } from '../api/dashboard.js'

const initialForm = () => ({
  customerId: '',
  meterId: '',
  readAt: alignedUtcSlot(),
  meterStatus: 'active',
  currentRead: '',
  previousRead: '',
  usageIndex: '',
  readType: 'actual',
  budgetIndicator: 'N',
  submittedBy: '',
  sourceReference: '',
})

export function FeedIngestionDialog({ onClose, onSubmitted }) {
  const [reference, setReference] = useState({ status: 'loading', pairs: [], error: null })
  const [form, setForm] = useState(initialForm)
  const [submission, setSubmission] = useState({ status: 'idle', message: '' })
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    getFeedReference({ signal: controller.signal })
      .then(({ data }) => setReference({ status: 'ready', pairs: data.pairs || [], error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setReference({ status: 'error', pairs: [], error })
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const focusedBeforeOpen = document.activeElement
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') return onClose()
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])')
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
      if (focusedBeforeOpen instanceof HTMLElement) focusedBeforeOpen.focus()
    }
  }, [onClose])

  const customers = useMemo(() => [...new Set(reference.pairs.map((pair) => pair.customerId))], [reference.pairs])
  const meters = useMemo(() => reference.pairs.filter((pair) => pair.customerId === form.customerId).map((pair) => pair.meterId), [form.customerId, reference.pairs])
  const calculatedUsageIndex = usageIndexFromReads(form.currentRead, form.previousRead)

  const update = (key, value) => setForm((values) => ({ ...values, [key]: value }))
  const selectCustomer = (customerId) => setForm((values) => ({ ...values, customerId, meterId: '' }))

  const submit = async (event) => {
    event.preventDefault()
    setSubmission({ status: 'submitting', message: '' })
    try {
      const result = await submitFeedReading({ ...form, usageIndex: calculatedUsageIndex ?? '' })
      setSubmission({ status: 'success', message: result.message })
      onSubmitted?.(result)
    } catch (error) {
      setSubmission({ status: 'error', message: error.message })
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="feed-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="feed-dialog-title" aria-describedby="feed-dialog-description">
        <header className="dialog-header">
          <div>
            <p className="card-kicker">Latest reading intake</p>
            <h2 id="feed-dialog-title">Submit a four-hour meter reading</h2>
            <p id="feed-dialog-description">Validate the operational data required before spike investigation. Times use UTC and must align to a four-hour slot.</p>
          </div>
          <button className="dialog-close" ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close latest reading intake">×</button>
        </header>

        <div className="feed-intake-note"><span aria-hidden="true">✓</span><p><strong>Controlled intake.</strong> Customer–meter mapping, timestamp cadence, numeric values, and duplicate protection are validated server-side. A submitted reading is not a customer notification or a root-cause decision.</p></div>

        {reference.status === 'loading' && <p className="feed-loading">Loading known customer and meter mappings…</p>}
        {reference.status === 'error' && <p className="feed-error" role="alert">Could not load source mappings: {reference.error.message}</p>}
        {reference.status === 'ready' && <form className="feed-form" onSubmit={submit}>
          <fieldset disabled={submission.status === 'submitting'}>
            <legend>Reading details</legend>
            <div className="feed-form-grid">
              <Field label="Customer" required><select value={form.customerId} onChange={(event) => selectCustomer(event.target.value)} required><option value="">Select customer</option>{customers.map((customer) => <option key={customer} value={customer}>{customer}</option>)}</select></Field>
              <Field label="Meter" required><select value={form.meterId} onChange={(event) => update('meterId', event.target.value)} required disabled={!form.customerId}><option value="">Select meter</option>{meters.map((meter) => <option key={meter} value={meter}>{meter}</option>)}</select></Field>
              <Field label="Read time (UTC)" required><input type="datetime-local" step="60" value={form.readAt} onChange={(event) => update('readAt', event.target.value)} required /></Field>
              <Field label="Read type" required><select value={form.readType} onChange={(event) => update('readType', event.target.value)}><option value="actual">Actual reading</option><option value="estimated">Estimated reading</option></select></Field>
              <Field label="Current meter read" required><input inputMode="decimal" type="number" min="0" step="any" value={form.currentRead} onChange={(event) => update('currentRead', event.target.value)} required /></Field>
              <Field label="Previous meter read" required><input inputMode="decimal" type="number" min="0" step="any" value={form.previousRead} onChange={(event) => update('previousRead', event.target.value)} required /></Field>
              <Field label="Usage index" hint="Calculated automatically" required><input className="calculated-value" inputMode="decimal" type="number" min="0" step="any" value={calculatedUsageIndex ?? ''} readOnly required /></Field>
              <Field label="Meter status" required><select value={form.meterStatus} onChange={(event) => update('meterStatus', event.target.value)}><option value="active">Active</option><option value="maintenance">Maintenance</option><option value="inactive">Inactive</option></select></Field>
              <Field label="Budget indicator" required><select value={form.budgetIndicator} onChange={(event) => update('budgetIndicator', event.target.value)}><option value="N">No</option><option value="Y">Yes</option></select></Field>
              <Field label="Submitted by" required><input value={form.submittedBy} maxLength="128" onChange={(event) => update('submittedBy', event.target.value)} placeholder="Associate ID or name" required /></Field>
              <Field label="Source reference" hint="Optional"><input value={form.sourceReference} maxLength="255" onChange={(event) => update('sourceReference', event.target.value)} placeholder="File, device, or work-order reference" /></Field>
            </div>
          </fieldset>
          {submission.status === 'error' && <p className="feed-error" role="alert">{submission.message}</p>}
          {submission.status === 'success' && <p className="feed-success" role="status">{submission.message}</p>}
          <footer className="feed-form-footer"><p>Expected cadence: one reading per meter every four hours. Duplicate or off-slot readings are rejected.</p><button className="feed-submit" type="submit">{submission.status === 'submitting' ? 'Validating…' : 'Validate and submit'}</button></footer>
        </form>}
      </section>
    </div>
  )
}

function Field({ label, hint, required, children }) {
  return <label className="feed-field"><span>{label}{required && <b aria-hidden="true"> *</b>}{hint && <em>{hint}</em>}</span>{children}</label>
}

function alignedUtcSlot() {
  const now = new Date()
  now.setUTCMinutes(0, 0, 0)
  now.setUTCHours(Math.floor(now.getUTCHours() / 4) * 4)
  return now.toISOString().slice(0, 16)
}

function usageIndexFromReads(currentRead, previousRead) {
  if (currentRead === '' || previousRead === '') return null
  const current = Number(currentRead)
  const previous = Number(previousRead)
  if (!Number.isFinite(current) || !Number.isFinite(previous)) return null

  // Avoid exposing floating-point artefacts such as 1.2000000000000002.
  return String(Number((current - previous).toFixed(6)))
}
