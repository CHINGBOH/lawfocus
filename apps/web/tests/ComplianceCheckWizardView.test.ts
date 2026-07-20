import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ComplianceCheckWizardView from '../src/views/ComplianceCheckWizardView.vue'
import { useAuthStore } from '../src/stores/auth'
import type { ComplianceCheck, Page, RoleGrant, RuleSetSummary, Subject } from '../src/types/api'

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
    { path: '/compliance-checks/new', name: 'compliance-check-new', component: ComplianceCheckWizardView },
    { path: '/compliance-checks/:checkId', name: 'compliance-check-result', component: {} },
    { path: '/subjects/:subjectId/facts', name: 'subject-facts', component: {} },
  ],
})

const demoSubject: Subject = {
  id: 'subject-1',
  subject_type: 'LISTED_COMPANY',
  name: '演示上市公司',
  unified_credit_code: null,
  listed: true,
  exchange: 'SSE',
}

const demoRuleset: RuleSetSummary = {
  id: 'rs-1',
  code: 'GOV-SET',
  version_no: 1,
  name: '上市公司治理规则集',
  status: 'PUBLISHED',
  effective_from: '2026-01-01',
  effective_to: null,
}

const tenantGrants: RoleGrant[] = [{ role_code: 'COMPLIANCE_USER', tenant_id: 'tenant-1' }]

function mountView(grants: RoleGrant[] = tenantGrants) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 'test-token'
  auth.me = { user_id: 'u-1', email: 'demo@example.com', display_name: '演示用户', grants }
  return mount(ComplianceCheckWizardView, { global: { plugins: [router, pinia] } })
}

function mockCatalogs({ subjects = [demoSubject], rulesets = [demoRuleset] } = {}) {
  vi.mocked(apiGet).mockImplementation((path: string) => {
    if (path.startsWith('/subjects')) {
      const page: Page<Subject> = { items: subjects, page: 1, page_size: 200, total: subjects.length }
      return Promise.resolve(page)
    }
    if (path.startsWith('/rulesets')) return Promise.resolve(rulesets)
    if (path.startsWith('/compliance-checks/precheck')) {
      return Promise.resolve({
        items: [
          {
            rule_code: 'GOV-ORG-001', rule_name: '董事会存在性', status: 'TRUE',
            missing_facts: [], applicable_reason: null, excluded_reason: null,
          },
        ],
      })
    }
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

async function fillAndConfirm(wrapper: ReturnType<typeof mountView>) {
  await wrapper.findAll('select')[0].setValue('subject-1')
  await wrapper.findAll('select')[1].setValue('rs-1')
  await wrapper.find('input[type="checkbox"]').setValue(true)
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiPost).mockReset()
})

describe('ComplianceCheckWizardView', () => {
  it('loads subjects and published rulesets into the selectors', async () => {
    mockCatalogs()
    const wrapper = mountView()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/subjects?subject_type=LISTED_COMPANY&page_size=200')
    expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/rulesets\?status_filter=PUBLISHED&at=\d{4}-\d{2}-\d{2}$/))
    expect(wrapper.text()).toContain('演示上市公司')
    expect(wrapper.text()).toContain('上市公司治理规则集（v1）')
  })

  it('shows an inline error when subjects fail to load but keeps the ruleset list', async () => {
    vi.mocked(apiGet).mockImplementation((path: string) => {
      if (path.startsWith('/subjects')) return Promise.reject(new Error('network down'))
      if (path.startsWith('/rulesets')) return Promise.resolve([demoRuleset])
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('加载失败：network down')
    expect(wrapper.text()).toContain('上市公司治理规则集（v1）')
  })

  it('shows an empty hint when no published ruleset is effective at the evaluation date', async () => {
    mockCatalogs({ rulesets: [] })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('在该评价时点没有已发布且有效的规则集，请调整日期或联系规则中心发布规则集')
  })

  it('keeps the submit button disabled until subject, ruleset and confirmation are all set', async () => {
    mockCatalogs()
    const wrapper = mountView()
    await flushPromises()

    const submitButton = wrapper.find('button')
    expect(submitButton.attributes('disabled')).toBeDefined()

    await wrapper.findAll('select')[0].setValue('subject-1')
    await wrapper.findAll('select')[1].setValue('rs-1')
    // Confirmation checkbox is the final gate.
    expect(submitButton.attributes('disabled')).toBeDefined()

    await wrapper.find('input[type="checkbox"]').setValue(true)
    expect(submitButton.attributes('disabled')).toBeUndefined()
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('submits with an Idempotency-Key header and navigates to the result page', async () => {
    mockCatalogs()
    const check: ComplianceCheck = {
      id: 'check-1',
      tenant_id: 'tenant-1',
      subject_id: 'subject-1',
      evaluation_time: '2026-07-18T00:00:00Z',
      rule_set_id: 'rs-1',
      ruleset_snapshot: [],
      status: 'COMPLETED',
      conclusions: [],
      deprecations: [],
    }
    vi.mocked(apiPost).mockResolvedValueOnce(check)
    const pushSpy = vi.spyOn(router, 'push').mockResolvedValue(undefined)

    const wrapper = mountView()
    await flushPromises()
    await fillAndConfirm(wrapper)
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith(
      '/compliance-checks',
      {
        tenant_id: 'tenant-1',
        subject_id: 'subject-1',
        evaluation_time: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T00:00:00Z$/),
        ruleset_id: 'rs-1',
      },
      { 'Idempotency-Key': expect.any(String) },
    )
    expect(pushSpy).toHaveBeenCalledWith({ name: 'compliance-check-result', params: { checkId: 'check-1' } })
    pushSpy.mockRestore()
  })

  it('shows the backend error and re-enables the button when submission fails', async () => {
    mockCatalogs()
    vi.mocked(apiPost).mockRejectedValueOnce(
      new ApiError(409, { code: 'IDEMPOTENCY_CONFLICT', message: '相同幂等键的请求体不一致', trace_id: 't-3' }),
    )
    const wrapper = mountView()
    await flushPromises()
    await fillAndConfirm(wrapper)
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('相同幂等键的请求体不一致')
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
  })

  it('blocks submission when the account has no tenant-scoped grant', async () => {
    mockCatalogs()
    const wrapper = mountView([{ role_code: 'READER', tenant_id: null }])
    await flushPromises()
    await fillAndConfirm(wrapper)
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('当前账号没有租户范围授权，无法发起检查')
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('reloads the ruleset list when the evaluation date changes', async () => {
    mockCatalogs()
    const wrapper = mountView()
    await flushPromises()

    const initialCalls = vi.mocked(apiGet).mock.calls.filter(([path]) => String(path).startsWith('/rulesets'))
    expect(initialCalls).toHaveLength(1)

    await wrapper.find('input[type="date"]').setValue('2026-06-30')
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/rulesets?status_filter=PUBLISHED&at=2026-06-30')
  })

  it('shows precheck results once subject and ruleset are both selected', async () => {
    mockCatalogs()
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('select')[0].setValue('subject-1')
    await wrapper.findAll('select')[1].setValue('rs-1')
    await flushPromises()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith(
      expect.stringMatching(/^\/compliance-checks\/precheck\?tenant_id=tenant-1&subject_id=subject-1.*&ruleset_id=rs-1$/),
    )
    expect(wrapper.text()).toContain('董事会存在性')
    expect(wrapper.text()).toContain('符合')
  })

  it('shows missing facts and a jump link when precheck reports UNKNOWN', async () => {
    vi.mocked(apiGet).mockImplementation((path: string) => {
      if (path.startsWith('/subjects')) {
        const page: Page<Subject> = { items: [demoSubject], page: 1, page_size: 200, total: 1 }
        return Promise.resolve(page)
      }
      if (path.startsWith('/rulesets')) return Promise.resolve([demoRuleset])
      if (path.startsWith('/compliance-checks/precheck')) {
        return Promise.resolve({
          items: [
            {
              rule_code: 'GOV-ID-002', rule_name: '独立董事最低比例', status: 'UNKNOWN',
              missing_facts: ['BOARD_COMPOSITION.independent_director_count'],
              applicable_reason: null, excluded_reason: null,
            },
          ],
        })
      }
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('select')[0].setValue('subject-1')
    await wrapper.findAll('select')[1].setValue('rs-1')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('资料不足')
    expect(wrapper.text()).toContain('BOARD_COMPOSITION.independent_director_count')
    expect(wrapper.text()).toContain('去补充事实')
    expect(wrapper.find('a[href="/subjects/subject-1/facts"]').exists()).toBe(true)
  })

  it('shows a readable error and a retry button when precheck fails', async () => {
    vi.mocked(apiGet).mockImplementation((path: string) => {
      if (path.startsWith('/subjects')) {
        const page: Page<Subject> = { items: [demoSubject], page: 1, page_size: 200, total: 1 }
        return Promise.resolve(page)
      }
      if (path.startsWith('/rulesets')) return Promise.resolve([demoRuleset])
      if (path.startsWith('/compliance-checks/precheck')) {
        return Promise.reject(new Error('network down'))
      }
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('select')[0].setValue('subject-1')
    await wrapper.findAll('select')[1].setValue('rs-1')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('预检加载失败')
    expect(wrapper.text()).toContain('network down')
  })
})
