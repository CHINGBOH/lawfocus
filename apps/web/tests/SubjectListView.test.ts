import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import SubjectListView from '../src/views/SubjectListView.vue'
import type { Page, Subject } from '../src/types/api'

vi.mock('../src/api/client', () => ({
  apiGet: vi.fn(),
}))

const { apiGet } = await import('../src/api/client')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Stub for the router plugin's initial navigation to "/" (avoids a
    // "[Vue Router warn]: No match found" on mount).
    { path: '/', name: 'laws', component: {} },
    { path: '/subjects', name: 'subjects', component: SubjectListView },
    { path: '/subjects/:subjectId/governance', name: 'subject-governance', component: {} },
    { path: '/subjects/:subjectId/facts', name: 'subject-facts', component: {} },
  ],
})

describe('SubjectListView', () => {
  it('shows the empty state when there are no subjects', async () => {
    const empty: Page<Subject> = { items: [], page: 1, page_size: 100, total: 0 }
    vi.mocked(apiGet).mockResolvedValueOnce(empty)
    const wrapper = mount(SubjectListView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无已收录主体')
  })

  it('shows an error state with retry on failure', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('network down'))
    const wrapper = mount(SubjectListView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('renders each subject with links to governance and facts pages', async () => {
    const page: Page<Subject> = {
      items: [
        {
          id: 'subject-1',
          subject_type: 'LISTED_COMPANY',
          name: '演示上市公司',
          unified_credit_code: null,
          listed: true,
          exchange: 'SSE',
        },
      ],
      page: 1,
      page_size: 100,
      total: 1,
    }
    vi.mocked(apiGet).mockResolvedValueOnce(page)
    const wrapper = mount(SubjectListView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('演示上市公司')
    expect(wrapper.text()).toContain('SSE')
    const links = wrapper.findAll('a')
    expect(links.some((l) => l.text().includes('治理结构'))).toBe(true)
    expect(links.some((l) => l.text().includes('事实与证据'))).toBe(true)
  })
})
