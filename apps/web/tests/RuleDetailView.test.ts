import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import RuleDetailView from '../src/views/RuleDetailView.vue'
import { useAuthStore } from '../src/stores/auth'
import type { RoleGrant, RuleDetail } from '../src/types/api'

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
    { path: '/rules/:ruleId', name: 'rule-detail', component: RuleDetailView },
  ],
})

function makeRule(status: string): RuleDetail {
  return {
    id: 'rule-1',
    code: 'GOV-ID-001',
    name: '独立董事占比',
    latest_version: {
      id: 'rv-1',
      version_no: 1,
      status,
      modality: 'OBLIGATION',
      subject_type: 'LISTED_COMPANY',
      effective_from: '2026-01-01',
      effective_to: null,
      condition_expression: {},
      requirement_expression: { operator: 'gte_ratio', numerator: 1, denominator: 3 },
      submitted_by: 'editor-1',
      sources: [
        {
          relation_type: 'BASED_ON',
          article_version: {
            id: 'av-1',
            article_id: 'a-1',
            legal_version_id: 'v-1',
            chapter_no: '第一百二十一条',
            section_no: null,
            article_text: '上市公司设独立董事。',
            valid_from: '2024-07-01',
            valid_to: null,
            created_at: '2024-07-01T00:00:00Z',
          },
        },
      ],
      test_cases: [
        { id: 'tc-1', case_type: 'POSITIVE', expected_status: 'TRUE', input_facts: {}, not_applicable_reason: null },
        { id: 'tc-2', case_type: 'BOUNDARY', expected_status: 'FALSE', input_facts: {}, not_applicable_reason: null },
      ],
      review_decisions: [],
    },
  }
}

function mountView(grants: RoleGrant[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 'test-token'
  auth.me = { user_id: 'u-1', email: 'demo@example.com', display_name: '演示用户', grants }
  return mount(RuleDetailView, {
    props: { ruleId: 'rule-1' },
    global: { plugins: [router, pinia] },
  })
}

function actionButton(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  if (!button) throw new Error(`button not found: ${text}`)
  return button
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiPost).mockReset()
})

describe('RuleDetailView', () => {
  it('renders the rule detail with sources, test cases and review records', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('DRAFT'))
    const wrapper = mountView([{ role_code: 'KNOWLEDGE_EDITOR', tenant_id: null }])
    await flushPromises()

    expect(wrapper.text()).toContain('独立董事占比（GOV-ID-001）')
    expect(wrapper.text()).toContain('状态：DRAFT')
    expect(wrapper.text()).toContain('模态：OBLIGATION')
    expect(wrapper.text()).toContain('第一百二十一条（BASED_ON）')
    expect(wrapper.text()).toContain('测试案例（2）')
    expect(wrapper.text()).toContain('暂无审核记录。')
  })

  it('enables submit for an editor on a DRAFT and disables review/publish with role reasons', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('DRAFT'))
    const wrapper = mountView([{ role_code: 'KNOWLEDGE_EDITOR', tenant_id: null }])
    await flushPromises()

    expect(actionButton(wrapper, '提交审核').attributes('disabled')).toBeUndefined()
    expect(actionButton(wrapper, '法律审核').attributes('disabled')).toBeDefined()
    expect(actionButton(wrapper, '技术审核').attributes('disabled')).toBeDefined()
    expect(actionButton(wrapper, '发布').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前账号没有 LegalReviewer 权限')
    expect(wrapper.text()).toContain('当前账号没有 TechnicalReviewer 权限')
    expect(wrapper.text()).toContain('当前账号没有 Publisher 权限')
  })

  it('disables every action for an account without governance roles', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('DRAFT'))
    const wrapper = mountView([{ role_code: 'READER', tenant_id: 'tenant-1' }])
    await flushPromises()

    expect(actionButton(wrapper, '提交审核').attributes('disabled')).toBeDefined()
    expect(actionButton(wrapper, '法律审核').attributes('disabled')).toBeDefined()
    expect(actionButton(wrapper, '技术审核').attributes('disabled')).toBeDefined()
    expect(actionButton(wrapper, '发布').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前账号没有 KnowledgeEditor 权限')
  })

  it('gates actions by status: IN_REVIEW allows only the legal review, which posts LEGAL', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('IN_REVIEW'))
    vi.mocked(apiPost).mockResolvedValueOnce(undefined)
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('LEGAL_APPROVED'))
    // Editor + legal reviewer: the submit button is disabled by the status
    // gate (not by a missing role), and review/publish are role-gated.
    const wrapper = mountView([
      { role_code: 'KNOWLEDGE_EDITOR', tenant_id: null },
      { role_code: 'LEGAL_REVIEWER', tenant_id: null },
    ])
    await flushPromises()

    expect(actionButton(wrapper, '法律审核').attributes('disabled')).toBeUndefined()
    expect(actionButton(wrapper, '提交审核').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前状态为 IN_REVIEW，不可提交')
    expect(wrapper.text()).toContain('当前账号没有 TechnicalReviewer 权限')
    expect(wrapper.text()).toContain('当前账号没有 Publisher 权限')

    await actionButton(wrapper, '法律审核').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/rules/rule-1/reviews', {
      review_type: 'LEGAL',
      decision: 'APPROVED',
      comment: null,
    })
    // The view reloaded and now shows the post-review status.
    expect(wrapper.text()).toContain('状态：LEGAL_APPROVED')
  })

  it('runs the second half of the dual review: LEGAL_APPROVED allows the technical review', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('LEGAL_APPROVED'))
    vi.mocked(apiPost).mockResolvedValueOnce(undefined)
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('TECH_APPROVED'))
    // SYSTEM_ADMIN passes every role check, so the remaining disabled reasons
    // come purely from the status gate.
    const wrapper = mountView([{ role_code: 'SYSTEM_ADMIN', tenant_id: null }])
    await flushPromises()

    expect(actionButton(wrapper, '技术审核').attributes('disabled')).toBeUndefined()
    expect(actionButton(wrapper, '法律审核').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前状态为 LEGAL_APPROVED，不在法律审核阶段')
    expect(wrapper.text()).toContain('当前状态为 LEGAL_APPROVED，不可提交')
    expect(wrapper.text()).toContain('当前状态为 LEGAL_APPROVED，需处于 TECH_APPROVED 才能发布')

    await actionButton(wrapper, '技术审核').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/rules/rule-1/reviews', {
      review_type: 'TECHNICAL',
      decision: 'APPROVED',
      comment: null,
    })
    expect(wrapper.text()).toContain('状态：TECH_APPROVED')
  })

  it('requires a review comment when requesting changes', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('IN_REVIEW'))
    const wrapper = mountView([{ role_code: 'LEGAL_REVIEWER', tenant_id: null }])
    await flushPromises()

    await wrapper.find('select').setValue('CHANGES_REQUESTED')
    await actionButton(wrapper, '法律审核').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('退回时必须填写审核意见')
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('shows the publish gate failure reason returned by the backend', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('TECH_APPROVED'))
    vi.mocked(apiPost).mockRejectedValueOnce(
      new ApiError(422, {
        code: 'PUBLISH_GATE_FAILED',
        message: '测试用例 tc-2 期望 FALSE，实际 TRUE',
        trace_id: 't-6',
      }),
    )
    const wrapper = mountView([{ role_code: 'PUBLISHER', tenant_id: null }])
    await flushPromises()

    expect(actionButton(wrapper, '发布').attributes('disabled')).toBeUndefined()
    await actionButton(wrapper, '发布').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('发布门禁未通过：测试用例 tc-2 期望 FALSE，实际 TRUE')
  })

  it('publishes a TECH_APPROVED version and reloads the new status', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('TECH_APPROVED'))
    vi.mocked(apiPost).mockResolvedValueOnce({ id: 'rv-1', rule_code: 'GOV-ID-001', version_no: 1, status: 'PUBLISHED' })
    vi.mocked(apiGet).mockResolvedValueOnce(makeRule('PUBLISHED'))
    const wrapper = mountView([{ role_code: 'PUBLISHER', tenant_id: null }])
    await flushPromises()

    await actionButton(wrapper, '发布').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/rules/rule-1/publish', {})
    expect(wrapper.text()).toContain('状态：PUBLISHED')
  })
})
