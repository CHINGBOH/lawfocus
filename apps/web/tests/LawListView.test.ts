import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import LawListView from '../src/views/LawListView.vue'
import type { Law } from '../src/types/api'

vi.mock('../src/api/client', () => ({
  apiGet: vi.fn(),
}))

const { apiGet } = await import('../src/api/client')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'laws', component: LawListView },
    { path: '/laws/:lawCode/versions/:versionName/articles/:articleNo?', name: 'article-reader', component: {} },
  ],
})

describe('LawListView', () => {
  it('shows loading, then the empty state when the API returns no laws', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce([])
    const wrapper = mount(LawListView, { global: { plugins: [router] } })

    expect(wrapper.text()).toContain('加载中')
    await flushPromises()
    expect(wrapper.text()).toContain('暂无已收录法律')
  })

  it('shows an error state with a retry button when the API call fails', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('network down'))
    const wrapper = mount(LawListView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('renders each law with its versions once loaded', async () => {
    const laws: Law[] = [
      {
        id: 'law-1',
        code: 'DEMO-COMPANY-LAW',
        name: '演示公司法',
        document_type: 'LAW',
        issuer: null,
        jurisdiction: 'DEMO',
        versions: [
          {
            id: 'v-1',
            version_name: 'DEMO-v2',
            promulgated_at: null,
            effective_from: '2024-07-01',
            effective_to: null,
            status: 'ACTIVE',
          },
        ],
      },
    ]
    vi.mocked(apiGet).mockResolvedValueOnce(laws)
    const wrapper = mount(LawListView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('演示公司法')
    expect(wrapper.text()).toContain('DEMO-v2')
  })
})
