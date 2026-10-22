export function DashboardHeader({ isLoading, onRefresh, onOpenAssistant, isAssistantOpen, assistantAvailable, onOpenFeed }) {
  return (
    <header className="dashboard-header">
      <div className="brand-block">
        <h1 className="brand-wordmark" aria-label="MeterIQ">
          <span>Meter</span><span className="brand-iq">IQ</span>
        </h1>
      </div>
      <div className="header-actions">
        <button className="feed-toggle" type="button" onClick={onOpenFeed} aria-label="Submit latest meter reading" title="Submit latest reading">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7v10M7 12h10" /><path d="M5 4.75h10.5l3.5 3.5v11A1.75 1.75 0 0 1 17.25 21h-12A1.75 1.75 0 0 1 3.5 19.25v-12A2.5 2.5 0 0 1 6 4.75Z" /></svg>
        </button>
        <button className="refresh-button" type="button" onClick={onRefresh} disabled={isLoading} aria-label="Refresh dashboard data" title="Refresh data">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.5a8 8 0 1 1-2.2-5.55" /><path d="M20 4.5v4.25h-4.25" /><path d="M4 12.5a8 8 0 0 0 13.7 5.55" /><path d="M4 19.5v-4.25h4.25" /></svg>
        </button>
        <button className="assistant-toggle" type="button" onClick={onOpenAssistant} disabled={!assistantAvailable} aria-label="Open data assistant" aria-controls="data-assistant" aria-expanded={isAssistantOpen} title="Open data assistant">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 10.8a6.8 6.8 0 1 1-9.81 6.12L5 18.6l1.58-3.63A6.78 6.78 0 1 1 19 10.8Z" /><path d="M8.7 12.25h.01M11.85 12.25h.01" /><path className="assistant-spark" d="m17.15 3 .68 1.72L19.55 5.4l-1.72.68-.68 1.72-.68-1.72-1.72-.68 1.72-.68L17.15 3Z" /></svg>
        </button>
      </div>
    </header>
  )
}
