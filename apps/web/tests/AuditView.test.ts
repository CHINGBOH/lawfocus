import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import AuditView from '../src/views/AuditView.vue'
import type { AuditEvent, Page } from '../src/types/api'

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client')
  return {
    ...actual,
    apiGet: vi.fn(),
  }
})

const { apiGet, ApiError } = await import('../src/api/client')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // The router plugin performs an initial navigation to "/" on install —
    // without this stub it logs "[Vue Router warn]: No match found".
    { path: '/', name: 'laws', component: {} },
    { path: '/audit', name: 'audit', component: AuditView },
    { path: '/rules/:ruleId', name: 'rule-detail', component: {} },
    { path: '/compliance-checks/:checkId', name: 'compliance-check-result', component: {} },
  ],
})

describe('AuditView', () => {
  it('shows a forbidden message when the account lacks Auditor role', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(
      new ApiError(403, { code: 'FORBIDDEN', message: 'insufficient role', trace_id: 't-1' }),
    )
    const wrapper = mount(AuditView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('没有 Auditor 权限')
  })

  it('shows the empty state when there are no matching events', async () => {
    const empty: Page<AuditEvent> = { items: [], page: 1, page_size: 50, total: 0 }
    vi.mocked(apiGet).mockResolvedValueOnce(empty)
    const wrapper = mount(AuditView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('没有符合条件的审计记录')
  })

  it('renders events with a clickable link for rule resources', async () => {
    const page: Page<AuditEvent> = {
      items: [
        {
          id: 'evt-1',
          trace_id: 'trace-abc',
          actor_id: 'user-1',
          tenant_id: null,
          action: 'PUBLISH',
          resource_type: 'rule',
          resource_id: 'rule-1',
          resource_version: '1',
          decision: 'DENIED',
          reason_code: 'PUBLISH_GATE_FAILED',
          occurred_at: '2026-01-01T00:00:00Z',
        },
      ],
      page: 1,
      page_size: 50,
      total: 1,
    }
    vi.mocked(apiGet).mockResolvedValueOnce(page)
    const wrapper = mount(AuditView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('PUBLISH_GATE_FAILED')
    expect(wrapper.text()).toContain('DENIED')
    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('rule:rule-1')
  })
})
