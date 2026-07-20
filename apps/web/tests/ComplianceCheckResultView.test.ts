import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import ComplianceCheckResultView from '../src/views/ComplianceCheckResultView.vue'
import type { ComplianceCheck, Conclusion, Subject, TruthValue } from '../src/types/api'

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
    { path: '/compliance-checks/:checkId', name: 'compliance-check-result', component: ComplianceCheckResultView },
    { path: '/conclusions/:conclusionId/proof', name: 'conclusion-proof', component: {} },
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

function makeConclusion(status: TruthValue, extra: Partial<Conclusion> = {}): Conclusion {
  return {
    id: `conc-${status.toLowerCase()}`,
    rule_version_id: 'rv-1',
    rule_code: 'GOV-ID-001',
    rule_name: '独立董事占比',
    result_status: status,
    missing_facts: [],
    applicable_reason: null,
    excluded_reason: null,
    ...extra,
  }
}

function makeCheck(conclusions: Conclusion[]): ComplianceCheck {
  return {
    id: 'check-1',
    tenant_id: 'tenant-1',
    subject_id: 'subject-1',
    evaluation_time: '2026-07-01T00:00:00Z',
    rule_set_id: 'rs-1',
    ruleset_snapshot: [],
    status: 'COMPLETED',
    conclusions,
    deprecations: [],
  }
}

function mockLoad(check: ComplianceCheck) {
  vi.mocked(apiGet).mockImplementation((path: string) => {
    if (path === '/compliance-checks/check-1') return Promise.resolve(check)
    if (path === '/subjects/subject-1') return Promise.resolve(demoSubject)
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

function mountView() {
  return mount(ComplianceCheckResultView, {
    props: { checkId: 'check-1' },
    global: { plugins: [router] },
  })
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
})

describe('ComplianceCheckResultView', () => {
  it('renders TRUE as 符合 with a next-step link to the proof', async () => {
    mockLoad(makeCheck([makeConclusion('TRUE', { applicable_reason: '独立董事人数满足要求' })]))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('主体：演示上市公司')
    expect(wrapper.text()).toContain('不汇总为单一合规分数')
    const card = wrapper.find('.conclusion-card')
    expect(card.text()).toContain('独立董事占比（GOV-ID-001）')
    expect(card.text()).toContain('符合')
    expect(card.text()).toContain('独立董事人数满足要求')

    const link = card.find('.next-step a')
    expect(link.text()).toContain('查看依据')
    expect(link.attributes('href')).toBe('/conclusions/conc-true/proof')
  })

  it('renders FALSE as 不符合 with a next-step link to the proof', async () => {
    mockLoad(makeCheck([makeConclusion('FALSE')]))
    const wrapper = mountView()
    await flushPromises()

    const card = wrapper.find('.conclusion-card')
    expect(card.text()).toContain('不符合')
    const link = card.find('.next-step a')
    expect(link.text()).toContain('查看差距与整改提示')
    expect(link.attributes('href')).toBe('/conclusions/conc-false/proof')
  })

  it('renders UNKNOWN as 资料不足, lists missing facts and links to the facts page', async () => {
    mockLoad(makeCheck([makeConclusion('UNKNOWN', { missing_facts: ['董事会独立董事人数'] })]))
    const wrapper = mountView()
    await flushPromises()

    const card = wrapper.find('.conclusion-card')
    expect(card.text()).toContain('资料不足')
    expect(card.text()).toContain('缺失事实：董事会独立董事人数')

    const link = card.find('.next-step a')
    expect(link.text()).toContain('跳转补充事实')
    expect(link.attributes('href')).toBe('/subjects/subject-1/facts')
  })

  it('renders CONFLICT as 事实或规则冲突 with a next-step link to the proof', async () => {
    mockLoad(makeCheck([makeConclusion('CONFLICT')]))
    const wrapper = mountView()
    await flushPromises()

    const card = wrapper.find('.conclusion-card')
    expect(card.text()).toContain('事实或规则冲突')
    const link = card.find('.next-step a')
    expect(link.text()).toContain('查看冲突来源')
    expect(link.attributes('href')).toBe('/conclusions/conc-conflict/proof')
  })

  it('renders NOT_APPLICABLE as 不适用 with the exclusion reason', async () => {
    mockLoad(makeCheck([makeConclusion('NOT_APPLICABLE', { excluded_reason: '该规则仅适用于主板上市公司' })]))
    const wrapper = mountView()
    await flushPromises()

    const card = wrapper.find('.conclusion-card')
    expect(card.text()).toContain('不适用')
    expect(card.text()).toContain('排除原因：该规则仅适用于主板上市公司')

    const link = card.find('.next-step a')
    expect(link.text()).toContain('查看排除原因')
    expect(link.attributes('href')).toBe('/conclusions/conc-not_applicable/proof')
  })

  it('shows the five-value disclaimer and no cards when the check has no conclusions', async () => {
    mockLoad(makeCheck([]))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('以下按规则逐条展示五值结论，不汇总为单一合规分数——五种状态含义不同，需分别处理')
    expect(wrapper.findAll('.conclusion-card')).toHaveLength(0)
  })

  it('shows a readable error and recovers via the retry button', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(
      new ApiError(403, { code: 'FORBIDDEN', message: '无权读取该检查结果', trace_id: 't-4' }),
    )
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('加载失败：无权读取该检查结果')

    mockLoad(makeCheck([makeConclusion('TRUE')]))
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('符合')
  })
})
