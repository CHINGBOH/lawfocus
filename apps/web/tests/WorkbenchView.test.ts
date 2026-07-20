import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import WorkbenchView from '../src/views/WorkbenchView.vue'
import { useAuthStore } from '../src/stores/auth'
import type { AuditEvent, ComplianceCheck, Page, RoleGrant, RuleOut } from '../src/types/api'

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
    // Stub for the router plugin's initial navigation to "/".
    { path: '/', name: 'laws', component: {} },
    { path: '/workbench', name: 'workbench', component: WorkbenchView },
    { path: '/rules/:ruleId', name: 'rule-detail', component: {} },
    { path: '/compliance-checks/:checkId', name: 'compliance-check-result', component: {} },
    { path: '/subjects/:subjectId/facts', name: 'subject-facts', component: {} },
  ],
})

const pendingRule: RuleOut = {
  id: 'rule-1',
  code: 'GOV-ID-001',
  name: '独立董事占比',
  latest_version: { id: 'rv-1', rule_code: 'GOV-ID-001', version_no: 1, status: 'IN_REVIEW' },
}

const publishedRule: RuleOut = {
  id: 'rule-2',
  code: 'GOV-TIME-001',
  name: '任期限制',
  latest_version: { id: 'rv-2', rule_code: 'GOV-TIME-001', version_no: 1, status: 'PUBLISHED' },
}

const demoCheck: ComplianceCheck = {
  id: 'check-001',
  tenant_id: 'tenant-1',
  subject_id: 'subject-1',
  evaluation_time: '2026-07-01T00:00:00Z',
  rule_set_id: 'rs-1',
  ruleset_snapshot: [],
  status: 'COMPLETED',
  conclusions: [
    {
      id: 'conc-1',
      rule_version_id: 'rv-1',
      rule_code: 'GOV-ID-001',
      rule_name: '独立董事占比',
      result_status: 'UNKNOWN',
      missing_facts: ['董事会独立董事人数'],
      applicable_reason: null,
      excluded_reason: null,
    },
    {
      id: 'conc-2',
      rule_version_id: 'rv-3',
      rule_code: 'GOV-MEET-001',
      rule_name: '董事会会议频率',
      result_status: 'FALSE',
      missing_facts: [],
      applicable_reason: null,
      excluded_reason: null,
    },
  ],
  deprecations: [],
}

const demoReadEvent: AuditEvent = {
  id: 'evt-1',
  trace_id: 'trace-1',
  actor_id: 'u-1',
  tenant_id: 'tenant-1',
  action: 'VIEW',
  resource_type: 'article_version',
  resource_id: 'av-123456789',
  resource_version: null,
  decision: 'ALLOWED',
  reason_code: null,
  occurred_at: '2026-07-01T08:00:00Z',
}

function pageOf<T>(items: T[]): Page<T> {
  return { items, page: 1, page_size: 5, total: items.length }
}

function mockWorkbench({
  rules = [pendingRule, publishedRule],
  checks = [demoCheck],
  reads = [demoReadEvent],
  checksError = null as Error | null,
  rulesError = null as Error | null,
} = {}) {
  vi.mocked(apiGet).mockImplementation((path: string) => {
    if (path === '/rules') {
      return rulesError ? Promise.reject(rulesError) : Promise.resolve(rules)
    }
    if (path.startsWith('/compliance-checks')) {
      return checksError ? Promise.reject(checksError) : Promise.resolve(pageOf(checks))
    }
    if (path.startsWith('/audit-events')) return Promise.resolve(pageOf(reads))
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

const tenantGrants: RoleGrant[] = [{ role_code: 'COMPLIANCE_USER', tenant_id: 'tenant-1' }]

function mountView(grants: RoleGrant[] = tenantGrants) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 'test-token'
  auth.me = { user_id: 'u-1', email: 'demo@example.com', display_name: '演示用户', grants }
  return mount(WorkbenchView, { global: { plugins: [router, pinia] } })
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
})

describe('WorkbenchView', () => {
  it('renders pending reviews, recent checks, missing facts and high-risk items', async () => {
    mockWorkbench()
    const wrapper = mountView()
    await flushPromises()

    // 待审核规则只过滤 IN_REVIEW/LEGAL_APPROVED，已发布规则不出现。
    expect(wrapper.text()).toContain('独立董事占比（GOV-ID-001）')
    expect(wrapper.text()).not.toContain('任期限制')
    // 最近检查
    expect(wrapper.text()).toContain('检查 check-00')
    // 待补事实来自 UNKNOWN 结论
    expect(wrapper.text()).toContain('缺失 董事会独立董事人数')
    // 高风险结果来自 FALSE/CONFLICT 结论
    expect(wrapper.text()).toContain('董事会会议频率')
    expect(wrapper.text()).toContain('不符合')
    // 最近阅读
    expect(wrapper.text()).toContain('条文版本 av-12345')

    const hrefs = wrapper.findAll('a').map((link) => link.attributes('href'))
    expect(hrefs).toContain('/rules/rule-1')
    expect(hrefs).toContain('/compliance-checks/check-001')
    expect(hrefs).toContain('/subjects/subject-1/facts')
  })

  it('shows per-card empty hints when every feed is empty', async () => {
    mockWorkbench({ rules: [], checks: [], reads: [] })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无待审核规则。')
    expect(wrapper.text()).toContain('暂无合规检查记录。')
    expect(wrapper.text()).toContain('暂无资料不足的结论。')
    expect(wrapper.text()).toContain('暂无不符合或冲突结论。')
    expect(wrapper.text()).toContain('暂无阅读记录。')
  })

  it('keeps other cards working when the checks feed answers 403', async () => {
    mockWorkbench({
      checksError: new ApiError(403, { code: 'FORBIDDEN', message: 'insufficient role', trace_id: 't-7' }),
    })
    const wrapper = mountView()
    await flushPromises()

    // 403 显示为可理解的权限提示，而不是空态。
    expect(wrapper.text()).toContain('当前角色无权查看合规检查记录')
    expect(wrapper.text()).not.toContain('暂无合规检查记录。')
    // 其余卡片不受影响。
    expect(wrapper.text()).toContain('独立董事占比（GOV-ID-001）')
    expect(wrapper.text()).toContain('条文版本 av-12345')
  })

  it('never renders an interface error as an empty state', async () => {
    mockWorkbench({ rulesError: new Error('boom'), checks: [], reads: [] })
    const wrapper = mountView()
    await flushPromises()

    const rulesCard = wrapper.findAll('section.card')[0]
    expect(rulesCard.text()).toContain('boom')
    expect(rulesCard.text()).not.toContain('暂无待审核规则。')
  })

  it('marks tenant-scoped cards as not applicable when the account has no tenant grant', async () => {
    mockWorkbench()
    const wrapper = mountView([{ role_code: 'READER', tenant_id: null }])
    await flushPromises()

    expect(wrapper.text()).toContain('当前账号无租户范围，不适用。')
    const calledPaths = vi.mocked(apiGet).mock.calls.map(([path]) => String(path))
    expect(calledPaths.some((path) => path.startsWith('/compliance-checks'))).toBe(false)
    expect(calledPaths).toContain('/rules')
    expect(calledPaths.some((path) => path.startsWith('/audit-events'))).toBe(true)
  })
})
