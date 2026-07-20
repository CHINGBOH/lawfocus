import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ConceptHyperlink from '../src/components/ConceptHyperlink.vue'
import type { ConceptDetail } from '../src/types/api'

vi.mock('../src/api/client', () => ({
  apiGet: vi.fn(),
}))

const { apiGet } = await import('../src/api/client')

describe('ConceptHyperlink', () => {
  it('fetches and shows the concept definition + source only after being clicked', async () => {
    const detail: ConceptDetail = {
      id: 'concept-1',
      code: 'CONCEPT-BOARD',
      name: '董事会',
      concept_type: 'ORGAN',
      status: 'ACTIVE',
      definition: '公司的常设决策机构。',
      review_status: 'UNVERIFIED',
      valid_from: '2024-07-01',
      valid_to: null,
      sources: [
        {
          relation_type: 'DEFINED_BY',
          article_version: {
            id: 'av-1',
            article_id: 'a-1',
            legal_version_id: 'v-1',
            chapter_no: '第一百零八条',
            section_no: null,
            article_text: '上市公司应当设置董事会。',
            valid_from: '2024-07-01',
            valid_to: null,
            created_at: '2024-07-01T00:00:00Z',
          },
        },
      ],
    }
    vi.mocked(apiGet).mockResolvedValueOnce(detail)

    const wrapper = mount(ConceptHyperlink, {
      props: { conceptId: 'CONCEPT-BOARD', text: '董事会' },
    })

    expect(wrapper.find('.concept-popover').exists()).toBe(false)
    expect(apiGet).not.toHaveBeenCalled()

    await wrapper.find('button.concept-hyperlink').trigger('click')
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/concepts/CONCEPT-BOARD')
    expect(wrapper.text()).toContain('公司的常设决策机构。')
    expect(wrapper.text()).toContain('UNVERIFIED')
    expect(wrapper.text()).toContain('DEFINED_BY')
  })

  it('shows an error state when the concept lookup fails', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('boom'))

    const wrapper = mount(ConceptHyperlink, {
      props: { conceptId: 'CONCEPT-UNKNOWN', text: '未知概念' },
    })
    await wrapper.find('button.concept-hyperlink').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('加载失败')
  })
})
