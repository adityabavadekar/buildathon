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
import { SettingsView } from '@/components/views/SettingsView'
import { StatusView } from '@/components/views/StatusView'
import { NAV_SECTION_LABELS } from '@/lib/navigation'
import { CaseDetailDrawer } from '@/components/cases/CaseDetailDrawer'
import { CommandPalette } from '@/components/command/CommandPalette'

export default function DashboardPage() {
  const [activeSection, setActiveSection] = useState<NavSection>('overview')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState<boolean>(true)
  const [cases, setCases] = useState<RecoveryCase[]>([])
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
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)

  const [isOffline, setIsOffline] = useState<boolean>(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [hRes, cRes, aRes, pRes, sRes, statusRes] = await Promise.all([
        getHealth(),
        listCases().catch(() => ({
          total: 0,
          offset: 0,
          limit: 100,
          items: [],
        })),
        getAnalytics().catch(() => null),
        getPolicies().catch(() => null),
        getSettings().catch(() => null),
        getSystemStatus().catch(() => null),
      ])

      setHealth(hRes)
      setCases(cRes.items)
      setAnalytics(aRes)
      setPolicies(pRes)
      setSettings(sRes)
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
        <div className="z-50 flex w-full animate-pulse flex-col justify-between gap-3 border-b-4 border-red-950 bg-[#dc2626] px-6 py-3 font-mono text-sm font-extrabold tracking-wide text-white uppercase shadow-2xl sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <AlertOctagon className="h-5 w-5 shrink-0 animate-bounce" />
            <span className="text-sm font-extrabold tracking-wide sm:text-base">
              API OFFLINE:{' '}
              {connectionError || 'Unable to communicate with Recovery Engine'}
            </span>
          </div>
          <div className="flex items-center gap-3 self-end sm:self-auto">
            <span className="hidden font-mono text-xs opacity-90 md:inline">
              Auto-reconnecting...
            </span>
            <button
              type="button"
              onClick={() => {
                void fetchData()
              }}
              className="flex cursor-pointer items-center gap-1.5 rounded-control bg-white px-4 py-1.5 font-mono text-xs font-extrabold text-[#dc2626] shadow-md transition-colors hover:bg-white/90"
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
            setActiveSection(section)
          }}
          casesCount={cases.length}
          escalatedCount={escalatedCount}
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
                  loading={casesLoading}
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                  onNavigateToRecovery={() => {
                    setActiveSection('recovery')
                  }}
                  onRefresh={() => {
                    void fetchData()
                  }}
                />
              )}

              {activeSection === 'pipeline' && <PipelineView />}

              {(activeSection === 'transactions' ||
                activeSection === 'recovery') && (
                <RecoveryView
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
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
                <AnalyticsView
                  analytics={analytics}
                  loading={casesLoading}
                />
              )}

              {activeSection === 'agent' && (
                <AgentView
                  cases={cases}
                  status={systemStatus}
                  loading={casesLoading}
                  onRefresh={() => {
                    void fetchData()
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

              {(activeSection === 'settings' ||
                activeSection === 'settings-general') && (
                <SettingsView settings={settings} loading={casesLoading} />
              )}

              {activeSection === 'settings-integrations' && (
                <IntegrationsView
                  settings={settings}
                  status={systemStatus}
                  loading={casesLoading}
                  onRefresh={() => {
                    void fetchData()
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
        onNavigate={setActiveSection}
        onSelectCase={setSelectedCase}
        onSeed={() => {
          void fetchData()
        }}
        onReset={() => {
          void fetchData()
        }}
      />
    </div>
  )
}
