import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BarChart3,
  Bot,
  ClipboardCheck,
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
  | 'approvals'
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
  pipeline: 'Data Pipeline (dev)',
  workflows: 'Workflows',
  recovery: 'Recovery Cases',
  approvals: 'Awaiting Approval',
  agent: 'AI Agent Telemetry',
  policies: 'Merchant Policies',
  status: 'System Status',
  settings: 'Settings',
}

export const MAIN_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
  badgeKey?: 'cases' | 'escalated'
}[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  {
    id: 'transactions',
    label: 'Transactions',
    icon: Receipt,
    badgeKey: 'cases',
  },
  {
    id: 'approvals',
    label: 'Awaiting Approval',
    icon: ClipboardCheck,
    badgeKey: 'escalated',
  },
  { id: 'audit', label: 'Audit Log', icon: History },
]

export const OPERATIONS_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
  badgeKey?: 'cases' | 'escalated'
}[] = [
  { id: 'pipeline', label: 'Data Pipeline (dev)', icon: Radio },
  { id: 'agent', label: 'AI Agent Telemetry', icon: Bot },
  { id: 'status', label: 'System Status', icon: Activity },
]

export const SETTINGS_NAV_ITEMS: {
  id: NavSection
  label: string
  icon: LucideIcon
}[] = [
  {
    id: 'settings-general',
    label: 'General Settings',
    icon: SlidersHorizontal,
  },
  { id: 'settings-policies', label: 'Merchant Policies', icon: ShieldCheck },
  { id: 'settings-integrations', label: 'Integrations', icon: Unplug },
]

export const SETTINGS_GROUP_ICON = Settings

const ALL_NAV_SECTIONS: NavSection[] = [
  'overview',
  'analytics',
  'transactions',
  'audit',
  'settings-policies',
  'settings-general',
  'settings-integrations',
  'pipeline',
  'workflows',
  'recovery',
  'approvals',
  'agent',
  'policies',
  'status',
  'settings',
]

export function isNavSection(value: string): value is NavSection {
  return (ALL_NAV_SECTIONS as string[]).includes(value)
}

/** Parse a location hash such as "#analytics" into a section, if it names one. */
export function sectionFromHash(hash: string): NavSection | null {
  const raw = hash.replace(/^#/, '').trim()
  return raw && isNavSection(raw) ? raw : null
}

export function hashForSection(section: NavSection): string {
  return `#${section}`
}
