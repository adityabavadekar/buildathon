/**
 * Typed client for the backend. Every call routes through here, so auth headers,
 * request IDs, and error handling live in one place.
 */

/** Defaults to `/api`, which next.config.ts rewrites to the backend. */
const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_BASE_URL ?? '/api'

// LoginGate subscribes to this so an expired session re-shows login immediately.
type SessionExpiredListener = () => void
const sessionExpiredListeners = new Set<SessionExpiredListener>()

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener)
  return () => {
    sessionExpiredListeners.delete(listener)
  }
}

function notifySessionExpired(path: string): void {
  // /auth/* 401s are a failed login attempt, not an expired session.
  if (path.startsWith('/auth/')) {
    return
  }
  for (const listener of sessionExpiredListeners) {
    listener()
  }
}

export type RecoveryState =
  | 'ANALYSIS_QUEUED'
  | 'IN_DUNNING'
  | 'OUTREACH_PENDING'
  | 'RETRY_SCHEDULED'
  | 'RECOVERED'
  | 'FAILED'
  | 'ESCALATED'

export type ExperimentArm = 'TREATMENT' | 'HOLDOUT_CONTROL'

export type OperatorAutonomyMode =
  'FULL_AUTONOMY' | 'HUMAN_IN_THE_LOOP' | 'MONITORING_ONLY'

export interface OperatorModeState {
  mode: OperatorAutonomyMode
  reason: string
  updated_at: string
  updated_by: string
}

export interface ModelTelemetrySnapshot {
  model: string
  provider?: string
  version?: string | null
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
  call_id?: string | null
  latency_ms?: number
  confidence_score?: number
  used_fallback?: boolean
  fallback_reason?: string | null
  cache_hit?: boolean
  experiment_tag?: string | null
  config_snapshot?: Record<string, unknown> | null
  request_prompt?: string | null
  response_content?: string | null
  error_detail?: string | null
}

export interface AuditEntry {
  entry_id: string
  case_id: string
  actor: string
  from_state: RecoveryState | null
  to_state: RecoveryState | null
  event_name: string
  timestamp: string
  created_at?: string
  notes?: string | null
  decision_inputs: Record<string, unknown>
  decision_outputs: Record<string, unknown>
  cost_incurred_paise: number
  model_metadata?: ModelTelemetrySnapshot | null
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
  invoice_id?: string | null
  subscription_id?: string | null
  contact_email?: string | null
  contact_phone?: string | null
  campaign_id?: string | null
  user_ref?: string | null
  reference_id?: string | null
  experiment_tag?: string | null
  model_override?: string | null
  metadata?: Record<string, unknown>
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
  attempts_count: number
  retry_count: number
  outreach_count: number
  failure_event: RawFailureEvent
  campaign_id?: string | null
  user_ref?: string | null
  reference_id?: string | null
  contact_email?: string | null
  contact_phone?: string | null
  audit_trail: AuditEntry[]
  created_at: string
  updated_at: string
  net_recovered_value_paise: number
  is_opted_out?: boolean
  due_at?: string | null
  next_action?: string | null
  dunning_message_en?: string | null
  dunning_message_hi?: string | null
  payment_link_id?: string | null
  payment_link_url?: string | null
  payment_link_expires_at?: string | null
  /** Null outside state === 'ESCALATED'. Says WHY the case is paused there:
   * HUMAN_JUDGMENT (fraud suspicion, a policy-required approval, an explicit
   * MANUAL_ESCALATION plan) vs SYSTEM_ERROR (a failed live gateway call
   * needing a retry, not a merchant decision). Persisted at escalation time,
   * not inferred from audit_trail content.
   */
  escalation_reason: 'HUMAN_JUDGMENT' | 'SYSTEM_ERROR' | null
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

export interface ChannelPerformance {
  channel: string
  attempts_sent: number
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

export interface DailyMetricPoint {
  date: string
  total_transactions: number
  failed_count: number
  recovered_count: number
  escalated_count: number
  at_risk_paise: number
  recovered_paise: number
  net_recovered_value_paise: number
  recovery_rate_pct: number
}

export interface MonthlyMetricPoint {
  month: string
  total_transactions: number
  failed_count: number
  recovered_count: number
  escalated_count: number
  at_risk_paise: number
  recovered_paise: number
  net_recovered_value_paise: number
  recovery_rate_pct: number
}

export interface EscalationQueueItem {
  case_id: string
  customer_id: string
  payment_id: string
  payment_rail: string
  amount_paise: number
  expected_recoverable_value_paise: number
  estimated_recovery_probability: number
  escalation_reason: string
  recommended_action: string
  recommended_discount_bps: number
  attempts_count: number
  created_at: string
  state: string
}

export interface CampaignMetrics {
  campaign_id: string
  total_cases: number
  recovered_cases: number
  escalated_cases: number
  at_risk_paise: number
  recovered_paise: number
  net_recovered_value_paise: number
  recovery_rate_pct: number
  avg_amount_paise: number
}

export interface AnalyticsSummaryResponse {
  total_cases: number
  active_cases?: number
  escalated_cases?: number
  recovered_cases?: number
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
  live_executions: number
  simulated_executions: number
  simulated_cost_paise: number
  health_score: number
  health_score_available: boolean
  category_distribution: CategoryBreakdown[]
  intervention_performance: ChannelPerformance[]
  rail_performance: RailBreakdown[]
  time_series: TimePointStats[]
  time_to_recovery_buckets: TTRBucket[]
  daily_metrics?: DailyMetricPoint[]
  monthly_metrics?: MonthlyMetricPoint[]
  campaign_metrics?: CampaignMetrics[]
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
  max_attempts: number
  min_cooldown_hours: number
  max_discount_bps: number
  holdout_percentage: number
  require_human_above_paise: number
  allowed_channels: string[]
  rules: PolicyRuleDetail[]
}

export interface MerchantPolicyPayload {
  merchant_id: string
  max_attempts: number
  min_cooldown_hours: number
  max_discount_bps: number
  holdout_percentage: number
  require_human_above_paise: number
  allowed_channels: string[]
}

export interface SystemSettingsResponse {
  merchant_id?: string
  currency?: string
  environment: string
  webhook_ingress_url: string
  webhook_secret_configured: boolean
  razorpay_key_id: string | null
  razorpay_mode: string | null
  razorpay_account_id: string | null
  razorpay_account_name: string | null
  razorpay_account_type: string | null
  razorpay_account_status: string | null
  primary_llm_provider: string | null
  active_llm_model: string | null
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
  success_count?: number
  fallback_count?: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
  p50_latency_ms?: number
  p95_latency_ms?: number
  last_call_at?: string | null
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

export interface ExperimentMetric {
  experiment_tag: string
  model: string
  provider: string
  cohort_size: number
  recovered_count: number
  recovery_rate: number
  failed_count: number
  avg_latency_ms: number
  total_cost_usd: number
}

export interface CaseFilterParams {
  merchant_id?: string
  state?: string
  states?: string
  experiment_arm?: string
  experiment_arms?: string
  payment_rail?: string
  payment_rails?: string
  error_code?: string
  error_codes?: string
  error_source?: string
  amount_min_paise?: number
  amount_max_paise?: number
  created_after?: string
  created_before?: string
  occurred_after?: string
  occurred_before?: string
  attempts_min?: number
  attempts_max?: number
  recovered?: boolean
  opted_out?: boolean
  has_escalation?: boolean
  escalation_reason?: 'HUMAN_JUDGMENT' | 'SYSTEM_ERROR'
  customer_id?: string
  payment_id?: string
  invoice_id?: string
  subscription_id?: string
  campaign_id?: string
  user_ref?: string
  reference_id?: string
  q?: string
  model_used?: string
  sort_by?: string
  sort_dir?: string
  limit?: number
  offset?: number
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
    active_provider: string | null
    active_model: string | null
    deterministic_fallback_active: boolean
    circuit_breaker: string
    operator_mode?: string
    offline_fallback_operational: boolean
  }
  policy_enforcement: {
    guardrail_status: string
    max_attempts_cap: number
    cooldown_hours: number
    discount_cap_bps: number
    holdout_ratio_pct: number
  }
  timestamp: string
}

export interface PipelineOverviewResponse {
  counts: {
    QUEUED: number
    QUEUED_DUE_NOW: number
    QUEUED_FUTURE: number
    PROCESSING: number
    DONE: number
    FAILED: number
    DEAD: number
  }
  events_received_total: number
  events_received_last_minute: number
  events_processed_total: number
  events_processed_last_minute: number
  backlog_depth: number
  oldest_queued_age_seconds: number
  last_event_timestamp: string | null
}

export interface PipelineTimeseriesPoint {
  timestamp: string
  ingested: number
  processed: number
  failed: number
}

export interface PipelineHeatmapCell {
  day: number
  hour: number
  count: number
}

export interface FleetStatusResponse {
  is_running: boolean
  is_paused: boolean
  events_per_minute: number
  rails: string[]
  min_amount_paise: number
  max_amount_paise: number
  use_llm: boolean
  experiment_id: string | null
  events_emitted: number
  started_at: string | null
  last_emitted_at: string | null
}

export interface ScheduledJobItem {
  job_id: string
  case_id: string
  job_type: string
  due_at: string
  status: 'QUEUED' | 'PROCESSING' | 'DONE' | 'FAILED' | 'DEAD' | 'PENDING'
  idempotency_key: string
  attempts: number
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PatternAlert {
  alert_id: string
  run_id: string
  seed: number
  feature_scope: string
  dominant_category: string
  dominant_intervention: string
  member_count: number
  mean_amount_paise: number
  example_case_ids: string[]
  created_at: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`
  const response = await fetch(url, { credentials: 'include', ...options })

  if (!response.ok) {
    if (response.status === 401) {
      notifySessionExpired(path)
    }
    const body = await response.text().catch(() => '')
    throw new Error(
      `API error ${response.status.toString()} from ${path}: ${body || response.statusText}`,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

/**
 * Surfaces FastAPI's `detail` where the operator must act on the reason - a
 * lockout, a wrong password, an unconfigured OAuth client.
 */
async function requestWithDetail<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...options,
  })

  if (!response.ok) {
    if (response.status === 401) {
      notifySessionExpired(path)
    }
    let detail = response.statusText
    try {
      const body: unknown = await response.json()
      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
      ) {
        detail = body.detail
      }
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function listCases(
  params?: CaseFilterParams,
): Promise<CaseListResponse> {
  if (!params) {
    return request<CaseListResponse>('/cases?limit=50')
  }
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      query.set(key, String(val))
    }
  })
  return request<CaseListResponse>(`/cases?${query.toString()}`)
}

export function getCase(id: string): Promise<RecoveryCase> {
  return request<RecoveryCase>(`/cases/${encodeURIComponent(id)}`)
}

export function getCaseAudit(id: string): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(`/cases/${encodeURIComponent(id)}/audit`)
}

export function approveCase(
  id: string,
  notes: string,
  overrideDiscountBps?: number,
): Promise<RecoveryCase> {
  return requestWithDetail<RecoveryCase>(
    `/cases/${encodeURIComponent(id)}/approve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notes,
        override_discount_bps: overrideDiscountBps,
      }),
    },
  )
}

export function getAnalytics(): Promise<AnalyticsSummaryResponse> {
  return request<AnalyticsSummaryResponse>('/analytics')
}

export function getPatternAlerts(): Promise<PatternAlert[]> {
  return request<PatternAlert[]>('/analytics/patterns')
}

export interface RecoveryModelStatus {
  status: string
  version: string
  arch?: string
  trained_count: number
  cv_metrics: Record<string, unknown> | null
  recovery_time_trained?: boolean
  expected_outputs?: string[]
  holdout_metrics: Record<string, unknown> | null
}

export function getRecoveryModel(): Promise<RecoveryModelStatus> {
  return request<RecoveryModelStatus>('/analytics/recovery-model')
}

export function trainRecoveryModel(): Promise<RecoveryModelStatus> {
  return request<RecoveryModelStatus>('/analytics/recovery-model/train', {
    method: 'POST',
  })
}

export function getEscalationQueue(): Promise<EscalationQueueItem[]> {
  return request<EscalationQueueItem[]>('/analytics/escalations')
}

export function getPolicies(): Promise<PolicyResponse> {
  return request<PolicyResponse>('/policies')
}

export function updatePolicies(
  policy: MerchantPolicyPayload,
): Promise<PolicyResponse> {
  return request<PolicyResponse>('/policies', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  })
}

export function getSettings(): Promise<SystemSettingsResponse> {
  return request<SystemSettingsResponse>('/settings')
}

export function getLlmConfig(): Promise<LLMSettingsState> {
  return request<LLMSettingsState>('/settings/llm-config')
}

export function updateLlmConfig(
  state: LLMSettingsState,
): Promise<LLMSettingsState> {
  return request<LLMSettingsState>('/settings/llm-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state),
  })
}

export function getLlmReport(): Promise<LLMReportResponse> {
  return request<LLMReportResponse>('/settings/llm-report')
}

export function listExperiments(): Promise<ExperimentMetric[]> {
  return request<ExperimentMetric[]>('/experiments')
}

export function getOperatorMode(): Promise<OperatorModeState> {
  return request<OperatorModeState>('/operator/mode')
}

export function updateOperatorMode(
  mode: OperatorAutonomyMode,
  reason: string,
): Promise<OperatorModeState> {
  return request<OperatorModeState>('/operator/mode', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, reason, updated_by: 'operator' }),
  })
}

export function testGatewayConnection(): Promise<GatewayTestResponse> {
  return request<GatewayTestResponse>('/settings/test-gateway', {
    method: 'POST',
  })
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return request<SystemStatusResponse>('/simulation/status')
}

export function resetSimulation(): Promise<{ status: string }> {
  return request('/simulation/reset', {
    method: 'POST',
  })
}

export function simulateResolveCase(
  caseId: string,
  amountPaise?: number,
): Promise<{
  status: string
  case_id: string
  net_recovered_value_paise?: number
}> {
  return request('/simulation/resolve-case', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      amount_paise: amountPaise,
    }),
  })
}

export const resolveCaseSim = simulateResolveCase

export function getPipelineOverview(): Promise<PipelineOverviewResponse> {
  return request<PipelineOverviewResponse>('/pipeline/overview')
}

export function getPipelineTimeseries(
  bucketMinutes: number = 60,
  hours: number = 24,
): Promise<PipelineTimeseriesPoint[]> {
  return request<PipelineTimeseriesPoint[]>(
    `/pipeline/timeseries?bucket_minutes=${bucketMinutes.toString()}&hours=${hours.toString()}`,
  )
}

export function getPipelineHeatmap(): Promise<PipelineHeatmapCell[]> {
  return request<PipelineHeatmapCell[]>('/pipeline/heatmap')
}

export function getQueuedJobs(
  limit: number = 50,
  statuses?: string,
): Promise<ScheduledJobItem[]> {
  const query = statuses
    ? `/pipeline/queued?limit=${limit.toString()}&statuses=${encodeURIComponent(statuses)}`
    : `/pipeline/queued?limit=${limit.toString()}`
  return request<ScheduledJobItem[]>(query)
}

export function ingestSingleEvent(
  payload: Record<string, unknown>,
): Promise<{ status: string; case_id: string; job_id: string }> {
  return request('/pipeline/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function startFleetSimulation(
  config: Record<string, unknown>,
): Promise<FleetStatusResponse> {
  return request<FleetStatusResponse>('/pipeline/fleet/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
}

export function stopFleetSimulation(): Promise<FleetStatusResponse> {
  return request<FleetStatusResponse>('/pipeline/fleet/stop', {
    method: 'POST',
  })
}

export function pauseFleetSimulation(): Promise<FleetStatusResponse> {
  return request<FleetStatusResponse>('/pipeline/fleet/pause', {
    method: 'POST',
  })
}

export function resumeFleetSimulation(): Promise<FleetStatusResponse> {
  return request<FleetStatusResponse>('/pipeline/fleet/resume', {
    method: 'POST',
  })
}

export function getFleetStatus(): Promise<FleetStatusResponse> {
  return request<FleetStatusResponse>('/pipeline/fleet/status')
}

export interface GatewayCredentialStatus {
  configured: boolean
  key_id_masked: string | null
  webhook_secret_configured: boolean
  source: string
  updated_at: string | null
  updated_by: string | null
}

export function getGatewayCredentials(): Promise<GatewayCredentialStatus> {
  return request<GatewayCredentialStatus>('/settings/gateway-credentials')
}

/** Reads the backend's `detail` so a rejected CSV explains itself. */
export function importGatewayCredentials(
  file: File,
): Promise<GatewayCredentialStatus> {
  const form = new FormData()
  form.append('file', file)
  // No Content-Type: the browser sets the multipart boundary.
  return requestWithDetail<GatewayCredentialStatus>(
    '/settings/gateway-credentials/import',
    { method: 'POST', body: form },
  )
}

export function clearGatewayCredentials(): Promise<GatewayCredentialStatus> {
  return request<GatewayCredentialStatus>('/settings/gateway-credentials', {
    method: 'DELETE',
  })
}

export interface SearchSuggestion {
  value: string
  field: string
  kind: string
  case_count: number
}

export function suggestSearchTerms(
  q: string,
  limit = 8,
): Promise<SearchSuggestion[]> {
  const params = new URLSearchParams({ q, limit: limit.toString() })
  return request<SearchSuggestion[]>(
    `/cases/search/suggestions?${params.toString()}`,
  )
}

export interface OAuthConnectionStatus {
  configured: boolean
  connected: boolean
  account_id: string | null
  account_id_masked: string | null
  public_token: string | null
  scope: string | null
  mode: string | null
  token_expires_at: string | null
  refresh_expires_at: string | null
  connected_at: string | null
  access_token_expired: boolean
  refresh_token_expired: boolean
  redirect_uri: string
  required_scope: string
}

export function getOAuthStatus(): Promise<OAuthConnectionStatus> {
  return request<OAuthConnectionStatus>('/integrations/oauth/status')
}

/** Returns the Razorpay URL to send the sub-merchant to. */
export async function startOAuthConnect(): Promise<string> {
  const body = await requestWithDetail<{ authorize_url: string }>(
    '/integrations/oauth/authorize-url',
    { method: 'POST' },
  )
  return body.authorize_url
}

export function refreshOAuthConnection(): Promise<OAuthConnectionStatus> {
  return requestWithDetail<OAuthConnectionStatus>(
    '/integrations/oauth/refresh',
    {
      method: 'POST',
    },
  )
}

export function disconnectOAuth(): Promise<OAuthConnectionStatus> {
  return requestWithDetail<OAuthConnectionStatus>('/integrations/oauth', {
    method: 'DELETE',
  })
}

export interface SessionStatus {
  auth_enabled: boolean
  authenticated: boolean
  ttl_hours: number
}

export function getSessionStatus(): Promise<SessionStatus> {
  return request<SessionStatus>('/auth/session')
}

export function login(password: string): Promise<SessionStatus> {
  return requestWithDetail<SessionStatus>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function logout(): Promise<SessionStatus> {
  return requestWithDetail<SessionStatus>('/auth/logout', { method: 'POST' })
}
