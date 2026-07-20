import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import FactEvidenceView from '../src/views/FactEvidenceView.vue'
import { useAuthStore } from '../src/stores/auth'
import type { Evidence, Fact, Page, RoleGrant } from '../src/types/api'

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client')
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
  }
})

const { apiGet, apiPost, ApiError } = await import('../src/api/client')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Stub for the router plugin's initial navigation to "/".
    { path: '/', name: 'laws', component: {} },
    { path: '/subjects/:subjectId/facts', name: 'subject-facts', component: FactEvidenceView },
  ],
})

const demoFact: Fact = {
  id: 'fact-1',
  tenant_id: 'tenant-1',
  company_id: 'subject-1',
  fact_type: 'BOARD_COMPOSITION',
  predicate: 'independent_director_count',
  object_value: { total: 9, independent: 3 },
  valid_from: '2026-01-01',
  valid_to: null,
  created_at: '2026-01-02T00:00:00Z',
}

const demoEvidence: Evidence = {
  id: 'ev-1',
  tenant_id: 'tenant-1',
  evidence_type: 'AnnualReport',
  title: '2025 年年报',
  source_url: null,
  source_file: null,
  page_no: null,
  quote_text: '独立董事 3 人',
  published_at: null,
  created_at: '2026-01-02T00:00:00Z',
}

function factPage(items: Fact[]): Page<Fact> {
  return { items, page: 1, page_size: 50, total: items.length }
}

const tenantGrants: RoleGrant[] = [{ role_code: 'COMPLIANCE_USER', tenant_id: 'tenant-1' }]

function mountView(grants: RoleGrant[] = tenantGrants) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 'test-token'
  auth.me = { user_id: 'u-1', email: 'demo@example.com', display_name: '演示用户', grants }
  return mount(FactEvidenceView, {
    props: { subjectId: 'subject-1' },
    global: { plugins: [router, pinia] },
  })
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiPost).mockReset()
})

describe('FactEvidenceView', () => {
  it('loads and renders the fact list with validity intervals', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(factPage([demoFact]))
    const wrapper = mountView()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/facts?tenant_id=tenant-1&subject_id=subject-1')
    expect(wrapper.text()).toContain('BOARD_COMPOSITION')
    expect(wrapper.text()).toContain('independent_director_count')
    expect(wrapper.text()).toContain('2026-01-01 起')
  })

  it('shows the empty state when the subject has no facts', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(factPage([]))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('暂无事实记录。')
  })

  it('shows a readable message instead of an empty state when loading is forbidden', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(
      new ApiError(403, { code: 'FORBIDDEN', message: '没有该租户事实的读取权限', trace_id: 't-1' }),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('加载失败：没有该租户事实的读取权限')
    expect(wrapper.text()).not.toContain('暂无事实记录')
  })

  it('blocks loading when the account has no tenant-scoped grant', async () => {
    const wrapper = mountView([{ role_code: 'READER', tenant_id: null }])
    await flushPromises()

    expect(wrapper.text()).toContain('当前账号没有租户范围授权，无法查看事实')
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('recovers from a loading failure via the retry button', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('加载失败：network down')

    vi.mocked(apiGet).mockResolvedValueOnce(factPage([demoFact]))
    await wrapper.find('.fact-list-section button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('BOARD_COMPOSITION')
  })

  it('rejects invalid JSON in the fact form without calling the API', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(factPage([demoFact]))
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('textarea').setValue('not-json{')
    await wrapper.findAll('form')[0].trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('结构化值必须是合法 JSON')
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('surfaces the backend interval validation error when fact creation is rejected', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(factPage([demoFact]))
    vi.mocked(apiPost).mockRejectedValueOnce(
      new ApiError(422, { code: 'INVALID_INTERVAL', message: 'valid_from 必须早于 valid_to', trace_id: 't-2' }),
    )
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('form')[0].trigger('submit')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith(
      '/facts',
      expect.objectContaining({
        tenant_id: 'tenant-1',
        company_id: 'subject-1',
        fact_type: 'BOARD_COMPOSITION',
        predicate: 'independent_director_count',
        object_value: { total: 9, independent: 3 },
        valid_from: expect.any(String),
      }),
    )
    expect(wrapper.text()).toContain('valid_from 必须早于 valid_to')
  })

  it('creates evidence metadata and shows the linking hint', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(factPage([demoFact]))
    vi.mocked(apiPost).mockResolvedValueOnce(demoEvidence)
    const wrapper = mountView()
    await flushPromises()

    const evidenceForm = wrapper.findAll('form')[1]
    await evidenceForm.findAll('input')[1].setValue('2025 年年报')
    await evidenceForm.trigger('submit')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith(
      '/evidence',
      expect.objectContaining({ tenant_id: 'tenant-1', evidence_type: 'AnnualReport', title: '2025 年年报' }),
    )
    expect(wrapper.text()).toContain('证据已创建，可在上方事实列表中展开并点击"关联刚创建的证据"')
  })

  it('links the freshly created evidence to a fact and refreshes its detail', async () => {
    let linked = false
    vi.mocked(apiGet).mockImplementation((path: string) => {
      if (path.startsWith('/facts?')) return Promise.resolve(factPage([demoFact]))
      if (path === '/facts/fact-1') {
        return Promise.resolve({
          ...demoFact,
          evidence: linked ? [{ evidence: demoEvidence, support_type: 'DIRECT', confidence: null }] : [],
        })
      }
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    vi.mocked(apiPost).mockImplementation((path: string) => {
      if (path === '/evidence') return Promise.resolve(demoEvidence)
      if (path === '/facts/fact-1/evidence/ev-1') {
        linked = true
        return Promise.resolve(undefined)
      }
      return Promise.reject(new Error(`unexpected POST ${path}`))
    })

    const wrapper = mountView()
    await flushPromises()

    // Create the evidence first so the link button becomes available.
    const evidenceForm = wrapper.findAll('form')[1]
    await evidenceForm.findAll('input')[1].setValue('2025 年年报')
    await evidenceForm.trigger('submit')
    await flushPromises()

    // Expand the fact detail — no evidence linked yet.
    await wrapper.find('button.fact-summary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('该事实暂无关联证据。')

    await wrapper.find('button.link-btn').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/facts/fact-1/evidence/ev-1', { support_type: 'DIRECT' })
    // The detail was refreshed after linking and now shows the evidence.
    expect(wrapper.text()).toContain('2025 年年报（DIRECT）')
    expect(wrapper.text()).toContain('「独立董事 3 人」')
  })
})
