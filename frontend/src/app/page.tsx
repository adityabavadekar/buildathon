'use client'

import React, { useCallback, useEffect, useState } from 'react'
import {
  getAnalytics,
  getHealth,
  getPolicies,
  getSettings,
  getSystemStatus,
  listCases,
  resetSimulation,
  seedSimulation,
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

  const fetchData = useCallback(async () => {
    try {
      const [hRes, cRes, aRes, pRes, sRes, statusRes] = await Promise.all([
        getHealth().catch(() => null),
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
    } finally {
      setHealthLoading(false)
      setCasesLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchData()
    const interval = setInterval(() => {
      void fetchData()
    }, 10000)
    return () => {
      clearInterval(interval)
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

  const handleSeedBatch = async () => {
    await seedSimulation(50, true)
    void fetchData()
  }

  const handleResetData = async () => {
    await resetSimulation()
    void fetchData()
  }

  const escalatedCount = cases.filter((c) => c.state === 'ESCALATED').length

  return (
    <div className="flex min-h-screen bg-canvas text-ink font-sans antialiased">
      {/* 1. Left Sidebar Navigation */}
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
          onRefresh={() => {
            void fetchData()
          }}
          onOpenCommand={() => {
            setCommandOpen(true)
          }}
        />

        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          <div className="mx-auto max-w-6xl">
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

            {activeSection === 'recovery' && (
              <RecoveryView
                cases={cases}
                loading={casesLoading}
                onSelectCase={(c) => {
                  setSelectedCase(c)
                }}
                onRefresh={() => {
                  void fetchData()
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

            {activeSection === 'agent' && <AgentView cases={cases} />}

            {activeSection === 'policies' && (
              <PoliciesView policies={policies} loading={casesLoading} />
            )}

            {activeSection === 'audit' && <AuditView cases={cases} />}

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

      {/* 3. Global Slide-Over Case Detail Drawer */}
      <CaseDetailDrawer
        caseItem={selectedCase}
        onClose={() => {
          setSelectedCase(null)
        }}
        onActionComplete={() => {
          void fetchData()
        }}
      />

      {/* 4. Global Command Palette (⌘K) */}
      <CommandPalette
        open={commandOpen}
        onClose={() => {
          setCommandOpen(false)
        }}
        cases={cases}
        onSelectCase={(c) => {
          setSelectedCase(c)
        }}
        onNavigate={(sec) => {
          setActiveSection(sec)
        }}
        onSeed={() => {
          void handleSeedBatch()
        }}
        onReset={() => {
          void handleResetData()
        }}
      />
    </div>
  )
}
