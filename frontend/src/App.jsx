import { useState } from 'react'
import { DashboardHeader } from './components/DashboardHeader.jsx'
import { MetricCards } from './components/MetricCards.jsx'
import { OperationalReadings } from './components/OperationalReadings.jsx'
import { CustomerHistoryDialog } from './components/CustomerHistoryDialog.jsx'
import { DataAssistant } from './components/DataAssistant.jsx'
import { DashboardDetailDialog } from './components/DashboardDetailDialog.jsx'
import { ReadDetailDialog } from './components/ReadDetailDialog.jsx'
import { SpikeCharts } from './components/SpikeCharts.jsx'
import { TrendCard } from './components/TrendCard.jsx'
import { FeedIngestionDialog } from './components/FeedIngestionDialog.jsx'
import { TicketWorkspace } from './components/TicketWorkspace.jsx'
import { useDashboardData } from './hooks/useDashboardData.js'

export default function App() {
  const { status, data, backend, error, refresh } = useDashboardData()
  const [selectedRead, setSelectedRead] = useState(null)
  const [selectedCustomerHistory, setSelectedCustomerHistory] = useState(null)
  const [detailSelection, setDetailSelection] = useState(null)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [feedOpen, setFeedOpen] = useState(false)
  const [ticketCandidate, setTicketCandidate] = useState(null)
  const openCustomerHistory = (id, days = null) => {
    setSelectedRead(null)
    setDetailSelection(null)
    setAssistantOpen(false)
    setSelectedCustomerHistory({ id, days })
  }

  return (
    <>
      <a className="skip-link" href="#dashboard-content">Skip to dashboard content</a>
      <main className="dashboard-shell" id="dashboard-content" tabIndex="-1" aria-busy={status === 'loading'}>
      <DashboardHeader isLoading={status === 'loading'} onRefresh={refresh} onOpenAssistant={() => setAssistantOpen(true)} isAssistantOpen={assistantOpen} assistantAvailable={Boolean(data)} onOpenFeed={() => setFeedOpen(true)} />
      {status === 'error' && <ErrorState error={error} onRetry={refresh} />}
      {data && <DashboardContent data={data} onOpenDetails={setDetailSelection} onSelectRead={setSelectedRead} onSelectCustomer={openCustomerHistory} onCreateTicket={setTicketCandidate} />}
      {selectedRead && <ReadDetailDialog row={selectedRead} onClose={() => setSelectedRead(null)} onViewCustomer={openCustomerHistory} />}
      {detailSelection && <DashboardDetailDialog data={data} selection={detailSelection} onClose={() => setDetailSelection(null)} onSelectCustomer={openCustomerHistory} />}
      {selectedCustomerHistory && <CustomerHistoryDialog customer={selectedCustomerHistory.id} initialDays={selectedCustomerHistory.days} onClose={() => setSelectedCustomerHistory(null)} />}
      {data && <DataAssistant data={data} backend={backend} isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} onViewCustomer={openCustomerHistory} />}
      {feedOpen && <FeedIngestionDialog onClose={() => setFeedOpen(false)} onSubmitted={() => refresh()} />}
      {ticketCandidate && <TicketWorkspace candidate={ticketCandidate} onClose={() => setTicketCandidate(null)} onUpdated={() => refresh()} />}
      </main>
    </>
  )
}

function ErrorState({ error, onRetry }) {
  return (
    <section className="state-card error-state" role="alert">
      <div><strong>Could not reach the dashboard API</strong><p>{error.message} Start <code>python dashboard.py</code> on port 8000, then retry.</p></div>
      <button className="retry-button" type="button" onClick={onRetry}>Try again</button>
    </section>
  )
}

function DashboardContent({ data, onOpenDetails, onSelectRead, onSelectCustomer, onCreateTicket }) {
  return (
    <>
      <MetricCards data={data} onOpenDetails={onOpenDetails} />
      <TrendCard data={data} onSelectCustomer={onSelectCustomer} />
      <SpikeCharts data={data} onOpenDetails={onOpenDetails} onSelectRead={onSelectRead} />
      <OperationalReadings data={data} onSelectRead={onSelectRead} onSelectCustomer={onSelectCustomer} onCreateTicket={onCreateTicket} />
      <footer className="site-footer">© <strong>Nisource Inc.</strong> All rights reserved.</footer>
    </>
  )
}
