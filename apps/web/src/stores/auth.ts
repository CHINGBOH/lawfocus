import { defineStore } from 'pinia'
import { apiGet, apiPost, getAuthToken, setAuthToken } from '../api/client'
import type { Me } from '../types/api'

interface TokenResponse {
  access_token: string
  token_type: string
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getAuthToken() as string | null,
    error: null as string | null,
    me: null as Me | null,
  }),
  getters: {
    isAuthenticated: (state) => state.token !== null,
    // The first tenant-scoped grant — good enough for a single-tenant demo
    // session; a real multi-tenant UI would let the user switch among these.
    currentTenantId: (state) => state.me?.grants.find((g) => g.tenant_id !== null)?.tenant_id ?? null,
    roleCodes: (state) => state.me?.grants.map((g) => g.role_code) ?? [],
  },
  actions: {
    async login(email: string, password: string): Promise<void> {
      this.error = null
      try {
        const res = await apiPost<TokenResponse>('/auth/login', { email, password })
        setAuthToken(res.access_token)
        this.token = res.access_token
        this.me = await apiGet<Me>('/auth/me')
      } catch (err) {
        this.error = err instanceof Error ? err.message : 'login failed'
        throw err
      }
    },
    async fetchMe(): Promise<void> {
      if (!this.token) return
      this.me = await apiGet<Me>('/auth/me')
    },
    logout(): void {
      setAuthToken(null)
      this.token = null
      this.me = null
    },
  },
})
