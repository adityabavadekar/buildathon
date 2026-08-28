/**
 * Typed client for the backend.
 *
 * All backend calls go through here rather than scattering `fetch` across
 * components - one place to add auth headers, request IDs, and error handling.
 */

/**
 * Base URL for the API. Defaults to `/api`, which the Vite dev server proxies to
 * the backend (see vite.config.ts), so the browser sees a single origin in
 * development. Set VITE_API_BASE_URL to target a deployed backend.
 */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

export interface HealthResponse {
  status: 'ok'
  version: string
  env: string
  llm_providers: string[]
}

/** Thrown when the backend responds with a non-2xx status. */
export class ApiError extends Error {
  // Written as explicit fields rather than constructor parameter properties:
  // `erasableSyntaxOnly` (on by default in the Vite template) forbids the
  // shorthand, since it emits runtime code rather than being purely erasable.
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
  // Headers is used rather than an object spread: RequestInit['headers'] may be
  // an array or a Headers instance, and spreading either would produce garbage.
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
