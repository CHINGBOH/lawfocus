import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import ConclusionProofView from '../src/views/ConclusionProofView.vue'
import type { Proof, ProofStep } from '../src/types/api'

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
    { path: '/conclusions/:conclusionId/proof', name: 'conclusion-proof', component: ConclusionProofView },
    { path: '/rules/:ruleId', name: 'rule-detail', component: {} },
    { path: '/facts/:factId', name: 'fact-detail', component: {} },
  ],
})

function makeStep(sequenceNo: number, extra: Partial<ProofStep> = {}): ProofStep {
  return {
    sequence_no: sequenceNo,
    step_type: 'RULE_EVALUATION',
    rule_version_id: 'rv-1',
    rule_id: null,
    rule_code: null,
    input_facts: {},
    calculation: {},
    output_state: {},
    ...extra,
  }
}

function makeProof(steps: ProofStep[]): Proof {
  return { id: 'proof-1', conclusion_id: 'conc-1', root_step_id: null, steps }
}

function mountView() {
  return mount(ConclusionProofView, {
    props: { conclusionId: 'conc-1' },
    global: { plugins: [router] },
  })
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
})

describe('ConclusionProofView', () => {
  it('renders a drill link to the rule when a step references rule_id', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(
      makeProof([
        makeStep(1, {
          rule_id: 'rule-1',
          rule_code: 'GOV-ID-001',
          calculation: { requirement: { operator: 'gte', value: 2, unit: 'person' } },
        }),
      ]),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/conclusions/conc-1/proof')
    expect(wrapper.text()).toContain('第 1 步：RULE_EVALUATION')
    const link = wrapper.find('.drill-link a')
    expect(link.text()).toContain('查看规则 GOV-ID-001')
    expect(link.attributes('href')).toBe('/rules/rule-1')
  })

  it('renders a single fact link when the calculation read one fact_id', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(
      makeProof([makeStep(1, { calculation: { fact_id: 'fact-1', lhs: 6, rhs: 2 } })]),
    )
    const wrapper = mountView()
    await flushPromises()

    const links = wrapper.findAll('.drill-link a')
    expect(links).toHaveLength(1)
    expect(links[0].text()).toContain('查看事实')
    expect(links[0].attributes('href')).toBe('/facts/fact-1')
  })

  it('renders one link per fact when the calculation read multiple fact_ids', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(
      makeProof([makeStep(1, { calculation: { fact_ids: ['fact-1', 'fact-2'], note: '交叉验证' } })]),
    )
    const wrapper = mountView()
    await flushPromises()

    const links = wrapper.findAll('.drill-link a')
    expect(links).toHaveLength(2)
    expect(links[0].attributes('href')).toBe('/facts/fact-1')
    expect(links[1].attributes('href')).toBe('/facts/fact-2')
  })

  it('renders no drill links for a step without rule or fact references', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(
      makeProof([makeStep(1, { calculation: { note: '纯文本步骤，无外部引用' } })]),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findAll('.drill-link')).toHaveLength(0)
    expect(wrapper.text()).toContain('纯文本步骤，无外部引用')
  })

  it('shows a readable error on 403 and recovers via the retry button', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(
      new ApiError(403, { code: 'FORBIDDEN', message: '无权查看证明链', trace_id: 't-5' }),
    )
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('加载失败：无权查看证明链')

    vi.mocked(apiGet).mockResolvedValueOnce(makeProof([makeStep(1)]))
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('第 1 步：RULE_EVALUATION')
  })
})
