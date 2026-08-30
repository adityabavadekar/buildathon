/**
 * Typed client for the backend.
 *
 * All backend calls go through here rather than scattering `fetch` across
 * components - one place to add auth headers, request IDs, and error handling.
 */

/**
 * Base URL for the API. Defaults to `/api`, which Next.js rewrites to
 * the backend in development. Set NEXT_PUBLIC_API_BASE_URL to target a deployed backend.
 */
const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_BASE_URL ?? '/api'

export type RecoveryState =
  | 'ANALYSIS_QUEUED'
  | 'IN_DUNNING'
  | 'OUTREACH_PENDING'
  | 'RETRY_SCHEDULED'
  | 'RECOVERED'
  | 'FAILED'
  | 'ESCALATED'

export type ExperimentArm = 'TREATMENT' | 'HOLDOUT_CONTROL'

export interface AuditEntry {
  entry_id: string
  case_id: string
  actor: string
  from_state: RecoveryState | null
  to_state: RecoveryState
  reason: string
  event_name: string
  timestamp: string
  created_at?: string
  notes?: string
  decision_inputs: Record<string, unknown>
  decision_outputs: Record<string, unknown>
  cost_incurred_paise: number
  model_metadata?: {
    model: string
    input_tokens?: number
    output_tokens?: number
    cost_usd?: number
    call_id?: string
    latency_ms?: number
  } | null
}

export interface RawFailureEvent {
  event_id: string
  payment_id: string
  customer_id: string
  amount_paise: number
  currency: string
  payment_rail: string
  error_code: string
  error_description: string
  error_source?: string | null
  error_step?: string | null
  error_reason?: string | null
  npci_response_code?: string | null
  category?: string | null
  occurred_at: string
}

export interface RecoveryCase {
  case_id: string
  merchant_id: string
  state: RecoveryState
  experiment_arm: ExperimentArm
  amount_paise: number
  currency: string
  recovered_amount_paise: number
  discount_paise_granted: number
  total_cost_paise: number
  touches_count: number
  retry_count: number
  outreach_count: number
  failure_event: RawFailureEvent
  audit_trail: AuditEntry[]
  created_at: string
  updated_at: string
  net_recovered_value_paise: number
}

export interface CaseListResponse {
  total: number
  offset: number
  limit: number
  items: RecoveryCase[]
}

export interface HealthResponse {
  status: 'ok'
  version: string
  env: string
  llm_providers: string[]
}

/** Thrown when the backend responds with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number
  readonly requestId: string | null

  constructor(message: string, status: number, requestId: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')

  const method = init?.method ?? 'GET'
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })

  if (!response.ok) {
    throw new ApiError(
      `${method} ${path} failed: ${response.status.toString()} ${response.statusText}`,
      response.status,
      response.headers.get('x-request-id'),
    )
  }

  return response.json() as Promise<T>
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function listCases(params?: {
  state?: RecoveryState
  experiment_arm?: ExperimentArm
  limit?: number
  offset?: number
}): Promise<CaseListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.state) searchParams.set('state', params.state)
  if (params?.experiment_arm)
    searchParams.set('experiment_arm', params.experiment_arm)
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString()
  return request<CaseListResponse>(`/cases${query ? `?${query}` : ''}`)
}

export function getCase(caseId: string): Promise<RecoveryCase> {
  return request<RecoveryCase>(`/cases/${caseId}`)
}

export function getCaseAudit(caseId: string): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(`/cases/${caseId}/audit`)
}

export function approveCase(
  caseId: string,
  notes: string,
  overrideDiscountBps?: number,
): Promise<RecoveryCase> {
  return request<RecoveryCase>(`/cases/${caseId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      notes,
      override_discount_bps: overrideDiscountBps,
    }),
  })
}

export interface ChannelPerformance {
  intervention_type: string
  total_attempts: number
  successful_recoveries: number
  success_rate_pct: number
}

export interface CategoryBreakdown {
  category: string
  count: number
  percentage: number
}

export interface RailBreakdown {
  rail: string
  total_cases: number
  at_risk_paise: number
  recovered_paise: number
  recovery_rate_pct: number
}

export interface TimePointStats {
  label: string
  failed_paise: number
  recovered_paise: number
}

export interface TTRBucket {
  bucket: string
  count: number
  percentage: number
}

export interface AnalyticsSummaryResponse {
  total_cases: number
  total_at_risk_paise: number
  recovered_amount_paise: number
  net_recovered_value_paise: number
  overall_recovery_rate_pct: number
  treatment_total: number
  treatment_recovered: number
  treatment_recovery_rate_pct: number
  holdout_total: number
  holdout_recovered: number
  holdout_recovery_rate_pct: number
  attributable_lift_pct: number
  total_gateway_fees_paise: number
  total_communication_cost_paise: number
  total_discounts_granted_paise: number
  return_on_recovery_spend: number
  health_score: number
  recovery_streak: number
  category_distribution: CategoryBreakdown[]
  intervention_performance: ChannelPerformance[]
  rail_performance: RailBreakdown[]
  time_series: TimePointStats[]
  time_to_recovery_buckets: TTRBucket[]
}

export interface PolicyRuleDetail {
  id: string
  name: string
  description: string
  value: string
  enforced: boolean
}

export interface PolicyResponse {
  merchant_id: string
  max_touches: number
  min_cooldown_hours: number
  max_discount_bps: number
  holdout_percentage: number
  require_human_above_paise: number
  rules: PolicyRuleDetail[]
}

export interface SystemSettingsResponse {
  environment: string
  webhook_ingress_url: string
  webhook_secret_configured: boolean
  razorpay_key_id: string | null
  primary_llm_provider: string
  active_llm_model: string
  configured_llm_providers: string[]
  deterministic_fallback_active: boolean
}

export interface GatewayTestResponse {
  status: 'CONNECTED' | 'PARTIAL' | 'SANDBOX_SIM'
  latency_ms: number
  key_id: string
  hmac_ready: boolean
  webhook_url: string
  supported_rails: string[]
  message: string
}

export interface ProviderSetting {
  name: string
  label: string
  enabled: boolean
  priority: number
  active_model: string
  available_models: string[]
  has_api_key: boolean
}

export interface LLMSettingsState {
  providers: ProviderSetting[]
  timeout_seconds: number
  temperature: number
}

export interface ModelStatItem {
  model: string
  provider: string
  call_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
}

export interface LLMReportResponse {
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  average_latency_ms: number
  model_breakdown: ModelStatItem[]
  providers: ProviderSetting[]
}

export function getAnalytics(): Promise<AnalyticsSummaryResponse> {
  return request<AnalyticsSummaryResponse>('/analytics')
}

export function getPolicies(): Promise<PolicyResponse> {
  return request<PolicyResponse>('/policies')
}

export function getSettings(): Promise<SystemSettingsResponse> {
  return request<SystemSettingsResponse>('/settings')
}

export function getLlmConfig(): Promise<LLMSettingsState> {
  return request<LLMSettingsState>('/settings/llm-config')
}

export function updateLlmConfig(state: LLMSettingsState): Promise<LLMSettingsState> {
  return request<LLMSettingsState>('/settings/llm-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state),
  })
}

export function getLlmReport(): Promise<LLMReportResponse> {
  return request<LLMReportResponse>('/settings/llm-report')
}

export function testGatewayConnection(): Promise<GatewayTestResponse> {
  return request<GatewayTestResponse>('/settings/test-gateway', {
    method: 'POST',
  })
}

export interface SystemStatusResponse {
  system_status: string
  uptime_seconds: number
  environment: string
  database_cases_count: number
  active_recovery_queue: number
  escalated_queue_count: number
  gateway_integration: {
    provider: string
    mode: string
    authenticated: boolean
    key_id: string | null
    webhook_endpoint: string
    supported_rails: string[]
  }
  llm_engine: {
    configured_providers: string[]
    active_model: string
    circuit_breaker: string
    offline_fallback_operational: boolean
  }
  policy_enforcement: {
    guardrail_status: string
    max_touches_cap: number
    cooldown_hours: number
    discount_cap_bps: number
    holdout_ratio_pct: number
  }
  timestamp: string
}

export function seedSimulation(
  count: number = 25,
  simulateResolutions: boolean = true
): Promise<{ seeded_count: number; recovered_count: number; case_ids: string[] }> {
  return request('/simulation/seed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count, simulate_resolutions: simulateResolutions }),
  })
}

export function resetSimulation(): Promise<{ status: string; message: string }> {
  return request('/simulation/reset', {
    method: 'POST',
  })
}

export function resolveCaseSim(
  caseId: string,
  amountPaise?: number
): Promise<{ status: string; case_id: string; state: RecoveryState; net_recovered_value_paise: number }> {
  return request('/simulation/resolve-case', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, amount_paise: amountPaise }),
  })
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return request<SystemStatusResponse>('/simulation/status')
}
