'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { AlertOctagon, RefreshCw } from 'lucide-react'
import {
  getAnalytics,
  getHealth,
  getPolicies,
  getSettings,
  getSystemStatus,
  listCases,
  type AnalyticsSummaryResponse,
  type HealthResponse,
  type PolicyResponse,
  type RecoveryCase,
  type SystemSettingsResponse,
  type SystemStatusResponse,
} from '@/lib/api'
import { Sidebar, type NavSection } from '@/components/layout/Sidebar'
import { TopNav } from '@/components/layout/TopNav'
import { AgentView } from '@/components/views/AgentView'
import { AnalyticsView } from '@/components/views/AnalyticsView'
import { ApprovalsView } from '@/components/views/ApprovalsView'
import { AuditView } from '@/components/views/AuditView'
import { IntegrationsView } from '@/components/views/IntegrationsView'
import { OverviewView } from '@/components/views/OverviewView'
import { PipelineView } from '@/components/views/PipelineView'
import { PoliciesView } from '@/components/views/PoliciesView'
import { RecoveryView } from '@/components/views/RecoveryView'
import { StatusView } from '@/components/views/StatusView'
import {
  NAV_SECTION_LABELS,
  hashForSection,
  sectionFromHash,
} from '@/lib/navigation'
import { CaseDetailDrawer } from '@/components/cases/CaseDetailDrawer'
import { CommandPalette } from '@/components/command/CommandPalette'
import { LoginGate } from '@/components/auth/LoginGate'

function Dashboard() {
  const [activeSection, setActiveSection] = useState<NavSection>('overview')

  // The section lives in the URL hash so a screen can be linked to and survives
  // a reload; navigate() is the single writer, popstate the single reader.
  const navigate = useCallback((section: NavSection): void => {
    setActiveSection(section)
    if (window.location.hash !== hashForSection(section)) {
      window.history.pushState(null, '', hashForSection(section))
    }
  }, [])

  useEffect(() => {
    const applyHash = (): void => {
      const fromHash = sectionFromHash(window.location.hash)
      if (fromHash) {
        setActiveSection(fromHash)
      }
    }
    applyHash()
    window.addEventListener('popstate', applyHash)
    window.addEventListener('hashchange', applyHash)
    return () => {
      window.removeEventListener('popstate', applyHash)
      window.removeEventListener('hashchange', applyHash)
    }
  }, [])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState<boolean>(true)
  const [cases, setCases] = useState<RecoveryCase[]>([])
  const [casesTotal, setCasesTotal] = useState<number>(0)
  const [casesLoading, setCasesLoading] = useState<boolean>(true)
  const [analytics, setAnalytics] = useState<AnalyticsSummaryResponse | null>(
    null,
  )
  const [policies, setPolicies] = useState<PolicyResponse | null>(null)
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    null,
  )
  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null)
  const [commandOpen, setCommandOpen] = useState<boolean>(false)
  const [paletteSearch, setPaletteSearch] = useState<string>('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)

  const [isOffline, setIsOffline] = useState<boolean>(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)

  // Shared across the sidebar/topnav and most views regardless of which one is
  // active, so this stays a single top-level poll rather than per-view.
  const fetchData = useCallback(async () => {
    try {
      const [hRes, cRes, aRes, statusRes] = await Promise.all([
        getHealth(),
        listCases({ limit: 100 }).catch(() => ({
          total: 0,
          offset: 0,
          limit: 100,
          items: [],
        })),
        getAnalytics().catch(() => null),
        getSystemStatus().catch(() => null),
      ])

      setHealth(hRes)
      setCases(cRes.items)
      setCasesTotal(cRes.total)
      setAnalytics(aRes)
      setSystemStatus(statusRes)
      setLastRefreshedAt(new Date())
      setIsOffline(false)
      setConnectionError(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setIsOffline(true)
      setConnectionError(msg)
      setHealth(null)
    } finally {
      setHealthLoading(false)
      setCasesLoading(false)
    }
  }, [])

  // Policies and settings are only ever read by their own views (Policies,
  // Settings, Integrations), so unlike fetchData above they poll only while
  // one of those views is actually active instead of on every page.
  const policiesOrSettingsActive =
    activeSection === 'policies' ||
    activeSection === 'settings-policies' ||
    activeSection === 'settings-integrations'

  const fetchPoliciesAndSettings = useCallback(async () => {
    const [pRes, sRes] = await Promise.all([
      getPolicies().catch(() => null),
      getSettings().catch(() => null),
    ])
    setPolicies(pRes)
    setSettings(sRes)
  }, [])

  useEffect(() => {
    let active = true
    const initTimer = setTimeout(() => {
      if (active) void fetchData()
    }, 0)
    const interval = setInterval(() => {
      if (active) void fetchData()
    }, 10000)

    const handleOnline = () => {
      if (active) {
        setIsOffline(false)
        setConnectionError(null)
        void fetchData()
      }
    }
    const handleOffline = () => {
      if (active) {
        setIsOffline(true)
        setConnectionError('Browser Network Disconnected')
      }
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      active = false
      clearTimeout(initTimer)
      clearInterval(interval)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [fetchData])

  useEffect(() => {
    if (!policiesOrSettingsActive) {
      return
    }
    let active = true
    const initTimer = setTimeout(() => {
      if (active) void fetchPoliciesAndSettings()
    }, 0)
    const interval = setInterval(() => {
      if (active) void fetchPoliciesAndSettings()
    }, 10000)
    return () => {
      active = false
      clearTimeout(initTimer)
      clearInterval(interval)
    }
  }, [policiesOrSettingsActive, fetchPoliciesAndSettings])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCommandOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

  const escalatedCount =
    analytics?.escalated_cases !== undefined
      ? analytics.escalated_cases
      : cases.filter((c) => c.state === 'ESCALATED').length

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-surface-sunken">
      {isOffline && (
        <div className="z-50 flex w-full animate-pulse flex-col justify-between gap-3 border-b-4 border-red-950 bg-[#dc2626] px-6 py-3 text-sm font-extrabold tracking-wide text-white uppercase shadow-2xl sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <AlertOctagon className="h-5 w-5 shrink-0 animate-bounce" />
            <span className="text-sm font-extrabold tracking-wide sm:text-base">
              API OFFLINE:{' '}
              {connectionError || 'Unable to communicate with Recovery Engine'}
            </span>
          </div>
          <div className="flex items-center gap-3 self-end sm:self-auto">
            <span className="hidden text-xs opacity-90 md:inline">
              Auto-reconnecting...
            </span>
            <button
              type="button"
              onClick={() => {
                void fetchData()
              }}
              className="flex cursor-pointer items-center gap-1.5 rounded-control bg-white px-4 py-1.5 text-xs font-extrabold text-[#dc2626] shadow-md transition-colors hover:bg-white/90"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry Connection</span>
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeSection={activeSection}
          onSelectSection={(section) => {
            navigate(section)
          }}
          casesCount={casesTotal}
          escalatedCount={escalatedCount}
          environment={systemStatus?.environment ?? null}
          razorpayKeyId={settings?.razorpay_key_id ?? null}
          razorpayMode={settings?.razorpay_mode ?? null}
          razorpayAccountName={settings?.razorpay_account_name ?? null}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          <TopNav
            title={NAV_SECTION_LABELS[activeSection]}
            health={health}
            analytics={analytics}
            healthLoading={healthLoading}
            lastRefreshedAt={lastRefreshedAt}
            onRefresh={() => {
              void fetchData()
            }}
            onOpenCommand={() => {
              setCommandOpen(true)
            }}
          />

          <main className="flex-1 overflow-y-auto p-6 lg:p-8">
            <div className="w-full min-w-0">
              {activeSection === 'overview' && (
                <OverviewView
                  cases={cases}
                  analytics={analytics}
                  status={systemStatus}
                  loading={casesLoading}
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                  onNavigateToRecovery={() => {
                    navigate('recovery')
                  }}
                  onNavigateToSection={(sec) => {
                    navigate(sec)
                  }}
                />
              )}

              {activeSection === 'pipeline' && (
                <PipelineView status={systemStatus} />
              )}

              {(activeSection === 'transactions' ||
                activeSection === 'recovery') && (
                <RecoveryView
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                  initialSearch={paletteSearch}
                />
              )}

              {activeSection === 'approvals' && (
                <ApprovalsView
                  cases={cases}
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                  onActionComplete={() => {
                    void fetchData()
                  }}
                />
              )}

              {activeSection === 'analytics' && (
                <AnalyticsView analytics={analytics} loading={casesLoading} />
              )}

              {activeSection === 'agent' && (
                <AgentView
                  cases={cases}
                  status={systemStatus}
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                />
              )}

              {(activeSection === 'policies' ||
                activeSection === 'settings-policies') && (
                <PoliciesView
                  policies={policies}
                  loading={casesLoading}
                  onSaved={(updated) => {
                    setPolicies(updated)
                  }}
                />
              )}

              {activeSection === 'audit' && (
                <AuditView
                  cases={cases}
                  refreshing={casesLoading}
                  onRefresh={() => {
                    void fetchData()
                  }}
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                />
              )}

              {activeSection === 'status' && (
                <StatusView
                  status={systemStatus}
                  loading={casesLoading}
                  onRefresh={() => {
                    void fetchData()
                  }}
                />
              )}

              {activeSection === 'settings-integrations' && (
                <IntegrationsView
                  settings={settings}
                  loading={casesLoading}
                  onRefresh={() => {
                    void fetchPoliciesAndSettings()
                  }}
                />
              )}
            </div>
          </main>
        </div>
      </div>

      {selectedCase && (
        <CaseDetailDrawer
          caseItem={selectedCase}
          onClose={() => {
            setSelectedCase(null)
          }}
          onActionComplete={() => {
            void fetchData()
          }}
        />
      )}

      <CommandPalette
        open={commandOpen}
        onClose={() => {
          setCommandOpen(false)
        }}
        cases={cases}
        onNavigate={navigate}
        onSelectCase={setSelectedCase}
        onSearchTerm={setPaletteSearch}
      />
    </div>
  )
}

export default function DashboardPage() {
  // The gate renders the dashboard only once the session is known good, so the
  // initial fetch does not fire a wall of 401s behind a login form.
  return (
    <LoginGate>
      <Dashboard />
    </LoginGate>
  )
}
