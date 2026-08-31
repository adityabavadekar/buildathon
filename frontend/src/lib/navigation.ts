import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BarChart3,
  Bot,
  Coins,
  GitBranch,
  History,
  LayoutDashboard,
  Radio,
  Receipt,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Unplug,
} from 'lucide-react'

export type NavSection =
  | 'overview'
  | 'analytics'
  | 'transactions'
  | 'audit'
  | 'settings-policies'
  | 'settings-general'
  | 'settings-integrations'
  | 'pipeline'
  | 'workflows'
  | 'recovery'
  | 'agent'
  | 'policies'
  | 'status'
  | 'settings'

export const SETTINGS_SECTIONS: NavSection[] = [
  'settings-policies',
  'settings-general',
  'settings-integrations',
  'policies',
  'settings',
]

export function isSettingsSection(section: NavSection): boolean {
  return SETTINGS_SECTIONS.includes(section)
}

export const NAV_SECTION_LABELS: Record<NavSection, string> = {
  overview: 'Overview',
  analytics: 'Analytics',
  transactions: 'Transactions',
  audit: 'Audit Log',
  'settings-policies': 'Merchant Policies',
  'settings-general': 'General Settings',
  'settings-integrations': 'Integrations',
  pipeline: 'Data Pipeline',
  workflows: 'Workflows',
  recovery: 'Recovery Cases',
  agent: 'AI Agent Telemetry',
  policies: 'Merchant Policies',
  status: 'System Status',
  settings: 'Settings',
}

export const MAIN_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
  badgeKey?: 'cases'
}[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'transactions', label: 'Transactions', icon: Receipt, badgeKey: 'cases' },
  { id: 'audit', label: 'Audit Log', icon: History },
]

export const OPERATIONS_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
  badgeKey?: 'cases'
}[] = [
  { id: 'pipeline', label: 'Data Pipeline', icon: Radio },
  { id: 'agent', label: 'Agent Telemetry', icon: Bot },
  { id: 'status', label: 'System Status', icon: Activity },
]

export const SETTINGS_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
}[] = [
  { id: 'settings-general', label: 'General Settings', icon: SlidersHorizontal },
  { id: 'settings-policies', label: 'Merchant Policies', icon: ShieldCheck },
  { id: 'settings-integrations', label: 'Integrations', icon: Unplug },
]

export const SETTINGS_GROUP_ICON = Settings
