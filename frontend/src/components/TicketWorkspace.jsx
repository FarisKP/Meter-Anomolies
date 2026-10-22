import { useMemo, useState } from 'react'
import { DashboardApiError, updateInvestigationTicket } from '../api/dashboard.js'

const CHECK_LABELS = {
  historical_baseline: 'Historical usage', weather: 'Weather', meter_changes: 'Meter changes',
  billing_issues: 'Billing issues', meter_anomalies: 'Meter anomalies',
  input_integrity: 'Input integrity', read_continuity: 'Read continuity', budget_indicator: 'Budget indicator',
}

const TEAMS = ['Meter Operations', 'Billing Resolution', 'Data Quality', 'Customer Care Review']
const STATUSES = [['open', 'Open'], ['in_progress', 'In progress'], ['awaiting_data', 'Awaiting data'], ['resolved', 'Resolved']]

function titleFor(code) { return CHECK_LABELS[code] || code.replaceAll('_', ' ') }
function evidenceState(outcome) { return outcome === 'pass' ? 'Available' : outcome === 'finding' ? 'Finding' : 'Needs data' }

function fallbackReport(investigation, evidence) {
  const findingLines = evidence.filter((item) => item.outcome === 'finding').map((item) => `- ${titleFor(item.checkCode)}: ${item.summary}`)
  const availableLines = evidence.filter((item) => item.outcome === 'pass').map((item) => `- ${titleFor(item.checkCode)}: ${item.summary}`)
  return ['Ticket summary', investigation.summary || 'The deterministic investigation is awaiting evidence.', '', 'Evidence requiring investigation', findingLines.join('\n') || '- No finding was generated.', '', 'Evidence reviewed and available', availableLines.join('\n') || '- No source returned usable evidence.'].join('\n')
}

function initialForm(investigation) {
  return {
    status: investigation.ticketStatus || 'open', assigned_team: investigation.assignedTeam || 'Meter Operations',
    title: investigation.title || `Usage spike review - ${investigation.ticketId || 'pending'}`,
    possible_cause: investigation.possibleCause || '', recommended_solution: investigation.recommendedSolution || '',
    associate_notes: investigation.associateNotes || '', last_edited_by: investigation.lastEditedBy || 'Associate', comment: '',
  }
}

export function TicketWorkspace({ candidate, onClose, onUpdated }) {
  const investigation = candidate.investigation || {}
  const hasTicket = Boolean(investigation.ticketId)
  const severity = investigation.severity || 'Pending'
  const evidence = Array.isArray(investigation.evidence) ? investigation.evidence.filter((item) => item.checkCode !== 'customer_changes') : []
  const report = investigation.detailedReport || fallbackReport(investigation, evidence)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(() => initialForm(investigation))
  const [comments, setComments] = useState(() => Array.isArray(investigation.comments) ? investigation.comments : [])
  const [saveState, setSaveState] = useState({ busy: false, error: '', notice: '' })
  const findings = useMemo(() => evidence.filter((item) => item.outcome === 'finding'), [evidence])
  const available = useMemo(() => evidence.filter((item) => item.outcome === 'pass'), [evidence])
  const setValue = (event) => setForm((previous) => ({ ...previous, [event.target.name]: event.target.value }))

  const save = async (event) => {
    event.preventDefault()
    if (!hasTicket) return
    setSaveState({ busy: true, error: '', notice: '' })
    try {
      await updateInvestigationTicket(investigation.ticketId, form)
      if (form.comment.trim()) setComments((previous) => [...previous, { commentId: `local-${Date.now()}`, author: form.last_edited_by || 'Associate', text: form.comment.trim(), createdAt: 'Saved just now' }])
      setForm((previous) => ({ ...previous, comment: '' }))
      setSaveState({ busy: false, error: '', notice: 'Ticket update saved.' })
      onUpdated?.()
    } catch (error) {
      const message = error instanceof DashboardApiError ? error.message : 'Could not save the ticket update.'
      setSaveState({ busy: false, error: message, notice: '' })
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="ticket-workspace" role="dialog" aria-modal="true" aria-labelledby="ticket-title">
        <header className="dialog-header">
          <div><p className="card-kicker">Deterministic investigation agent</p><h2 id="ticket-title">Automated investigation report</h2><p>Evidence is generated server-side. Associates can document and route the ticket, but cannot overwrite retained source evidence.</p></div>
          <button className="dialog-close" type="button" onClick={onClose} aria-label="Close investigation report">×</button>
        </header>
        <div className="ticket-hero"><span className={`ticket-severity ticket-severity--${severity.toLowerCase()}`}>{severity}</span><div><strong>{hasTicket ? investigation.ticketId : 'Automatic ticket recovery pending'}</strong><p>{investigation.summary || 'The spike candidate is queued. The server must complete its deterministic investigation before a ticket can be opened.'}</p></div></div>
        <div className="ticket-layout">
          <section className="ticket-evidence">
            <h3>Investigation report</h3>
            <article className="ticket-narrative"><strong>Deterministic evidence summary</strong><p>{report}</p></article>
            <div className="ticket-evidence-groups">
              <div><h4>Findings to investigate <span>{findings.length}</span></h4>{findings.length ? findings.map((item) => <EvidenceItem key={item.checkCode} item={item} />) : <p className="ticket-empty">No additional findings.</p>}</div>
              <div><h4>Controls reviewed <span>{available.length}</span></h4>{available.length ? available.map((item) => <EvidenceItem key={item.checkCode} item={item} />) : <p className="ticket-empty">No supporting evidence available.</p>}</div>
            </div>
          </section>
          <aside className="ticket-preview">
            <div className="ticket-preview-heading"><p className="card-kicker">Generated ticket</p>{hasTicket && <button className="ticket-edit-toggle" type="button" onClick={() => setEditing((value) => !value)}>{editing ? 'Cancel edit' : 'Edit ticket'}</button>}</div>
            {!editing && <ReadOnlyTicket investigation={investigation} comments={comments} />}
            {editing && <TicketEditor form={form} saveState={saveState} onChange={setValue} onSave={save} />}
            {!editing && <p className="ticket-footnote">System evidence is retained separately. Choose “Edit ticket” to assign, update the resolution plan, or add associate comments.</p>}
          </aside>
        </div>
      </section>
    </div>
  )
}

function EvidenceItem({ item }) {
  return <article className="ticket-check"><div><strong>{titleFor(item.checkCode)}</strong><p>{item.summary}</p></div><span className={item.outcome === 'pass' ? 'ticket-state ticket-state--ready' : 'ticket-state'}>{evidenceState(item.outcome)}</span></article>
}

function ReadOnlyTicket({ investigation, comments }) {
  return <>
    <dl><div><dt>Ticket ID</dt><dd>{investigation.ticketId || 'Pending'}</dd></div><div><dt>Status</dt><dd>{String(investigation.ticketStatus || 'Recovery required').replaceAll('_', ' ')}</dd></div><div><dt>Assigned team</dt><dd>{investigation.assignedTeam || 'Pending evidence'}</dd></div><div><dt>Possible cause</dt><dd>{investigation.possibleCause || 'Evidence collection has not completed.'}</dd></div><div><dt>Recommended solution</dt><dd>{investigation.recommendedSolution || 'Retry the deterministic investigation after the required data sources are available.'}</dd></div>{investigation.associateNotes && <div><dt>Associate notes</dt><dd>{investigation.associateNotes}</dd></div>}</dl>
    <CommentThread comments={comments} />
  </>
}

function TicketEditor({ form, saveState, onChange, onSave }) {
  return <form className="ticket-editor" onSubmit={onSave}>
    <label>Ticket title<input name="title" value={form.title} onChange={onChange} required maxLength="255" /></label>
    <label>Status<select name="status" value={form.status} onChange={onChange}>{STATUSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
    <label>Assigned team<select name="assigned_team" value={form.assigned_team} onChange={onChange}>{TEAMS.map((team) => <option value={team} key={team}>{team}</option>)}</select></label>
    <label>Possible cause<textarea name="possible_cause" value={form.possible_cause} onChange={onChange} required maxLength="1000" rows="3" /></label>
    <label>Recommended solution<textarea name="recommended_solution" value={form.recommended_solution} onChange={onChange} required maxLength="2000" rows="4" /></label>
    <label>Associate assessment<textarea name="associate_notes" value={form.associate_notes} onChange={onChange} maxLength="4000" rows="4" placeholder="Document validation performed, next owner, or a decision rationale." /></label>
    <label>Comment author<input name="last_edited_by" value={form.last_edited_by} onChange={onChange} required maxLength="128" /></label>
    <label>Add comment<textarea name="comment" value={form.comment} onChange={onChange} maxLength="2000" rows="3" placeholder="Add an auditable progress update (optional)." /></label>
    {saveState.error && <p className="ticket-save-error" role="alert">{saveState.error}</p>}
    {saveState.notice && <p className="ticket-save-notice" role="status">{saveState.notice}</p>}
    <button className="ticket-create" type="submit" disabled={saveState.busy}>{saveState.busy ? 'Saving ticket…' : 'Save ticket update'}</button>
  </form>
}

function CommentThread({ comments }) {
  if (!comments.length) return <section className="ticket-comments"><h3>Associate comments</h3><p>No associate comments yet.</p></section>
  return <section className="ticket-comments"><h3>Associate comments</h3>{comments.map((comment) => <article key={comment.commentId}><strong>{comment.author}</strong><time>{comment.createdAt}</time><p>{comment.text}</p></article>)}</section>
}
