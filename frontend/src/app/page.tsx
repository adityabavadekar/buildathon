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
import { AuditView } from '@/components/views/AuditView'
import { OverviewView } from '@/components/views/OverviewView'
import { PipelineView } from '@/components/views/PipelineView'
import { PoliciesView } from '@/components/views/PoliciesView'
import { RecoveryView } from '@/components/views/RecoveryView'
import { SettingsView } from '@/components/views/SettingsView'
import { StatusView } from '@/components/views/StatusView'
import { CaseDetailDrawer } from '@/components/cases/CaseDetailDrawer'
import { CommandPalette } from '@/components/command/CommandPalette'

export default function DashboardPage() {
  const [activeSection, setActiveSection] = useState<NavSection>('overview')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState<boolean>(true)
  const [cases, setCases] = useState<RecoveryCase[]>([])
  const [casesLoading, setCasesLoading] = useState<boolean>(true)
  const [analytics, setAnalytics] = useState<AnalyticsSummaryResponse | null>(null)
  const [policies, setPolicies] = useState<PolicyResponse | null>(null)
  const [settings, setSettings] = useState<SystemSettingsResponse | null>(null)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null)
  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null)
  const [commandOpen, setCommandOpen] = useState<boolean>(false)
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)

  // API Offline & Connection Failure Tracking
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

  const escalatedCount = analytics?.escalated_cases !== undefined ? analytics.escalated_cases : cases.filter((c) => c.state === 'ESCALATED').length

  return (
    <div className="flex h-screen w-full flex-col bg-surface-sunken overflow-hidden">
      {/* High-Visibility Red Bold Top Banner when API Offline or Connection Issue */}
      {isOffline && (
        <div className="w-full bg-[#dc2626] text-white px-6 py-3 text-sm font-extrabold font-mono uppercase tracking-wide flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xl z-50 border-b-4 border-red-950 animate-pulse">
          <div className="flex items-center gap-3">
            <AlertOctagon className="h-5 w-5 shrink-0 animate-bounce" />
            <span className="font-extrabold text-sm sm:text-base tracking-wide">
              API OFFLINE: {connectionError || 'Unable to communicate with Recovery Engine'}
            </span>
          </div>
          <div className="flex items-center gap-3 self-end sm:self-auto">
            <span className="text-xs opacity-90 hidden md:inline font-mono">
              Auto-reconnecting...
            </span>
            <button
              type="button"
              onClick={() => {
                void fetchData()
              }}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-white text-[#dc2626] hover:bg-white/90 rounded-control text-xs font-extrabold font-mono transition-colors cursor-pointer shadow-md"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry Connection</span>
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* 1. Left Sidebar */}
        <Sidebar
          activeSection={activeSection}
          onSelectSection={(section) => {
            setActiveSection(section)
          }}
          casesCount={cases.length}
          escalatedCount={escalatedCount}
        />

        {/* 2. Main Content Area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <TopNav
            title={activeSection === 'status' ? 'System Status' : activeSection}
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
            <div className="mx-auto max-w-7xl">
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

              {activeSection === 'recovery' && (
                <RecoveryView
                  onSelectCase={(c) => {
                    setSelectedCase(c)
                  }}
                />
              )}

              {activeSection === 'analytics' && (
                <AnalyticsView
                  analytics={analytics}
                  policies={policies}
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

              {activeSection === 'policies' && (
                <PoliciesView policies={policies} loading={casesLoading} />
              )}

              {activeSection === 'audit' && (
                <AuditView
                  cases={cases}
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

              {activeSection === 'settings' && (
                <SettingsView settings={settings} loading={casesLoading} />
              )}
            </div>
          </main>
        </div>
      </div>

      {/* 3. Global Slide-Over Case Detail Drawer */}
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

      {/* 4. Keyboard Command Palette */}
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
