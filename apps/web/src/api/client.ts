import type { ApiErrorBody } from '../types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  code: string
  traceId: string
  status: number

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.status = status
    this.code = body.code
    this.traceId = body.trace_id
  }
}

let authToken: string | null = localStorage.getItem('lawfocus_token')

export function setAuthToken(token: string | null): void {
  authToken = token
  if (token) {
    localStorage.setItem('lawfocus_token', token)
  } else {
    localStorage.removeItem('lawfocus_token')
  }
}

export function getAuthToken(): string | null {
  return authToken
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (authToken) {
    headers.set('Authorization', `Bearer ${authToken}`)
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(
      response.status,
      body ?? { code: 'UNKNOWN_ERROR', message: response.statusText, trace_id: '' },
    )
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export function apiPost<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body), headers })
}
