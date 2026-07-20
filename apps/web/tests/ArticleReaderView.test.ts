import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import ArticleReaderView from '../src/views/ArticleReaderView.vue'
import type { ArticleNavigation, ArticleSummary, LegalVersion, RuleSynthesis, Synthesis } from '../src/types/api'

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
    { path: '/', name: 'laws', component: {} },
    {
      path: '/laws/:lawCode/versions/:versionName/articles/:articleNo?',
      name: 'article-reader',
      component: ArticleReaderView,
      props: true,
    },
  ],
})

const versions: LegalVersion[] = [
  {
    id: 'v-1',
    version_name: 'v1',
    promulgated_at: null,
    effective_from: '2024-01-01',
    effective_to: null,
    status: 'ACTIVE',
  },
]

// '1', '2', '10' — a lexicographic sort would place '10' before '2'; the
// component must trust the backend's numeric order, not re-sort client-side.
const directory: ArticleSummary[] = [
  { article_no: '1', chapter_no: '第一章', section_no: null, summary: '第一条摘要' },
  { article_no: '2', chapter_no: '第一章', section_no: null, summary: '第二条摘要' },
  { article_no: '10', chapter_no: '第二章', section_no: null, summary: '第十条摘要' },
]

function navFor(articleNo: string): ArticleNavigation {
  const index = directory.findIndex((d) => d.article_no === articleNo)
  return {
    current: {
      id: `av-${articleNo}`,
      article_id: `a-${articleNo}`,
      article_no: articleNo,
      legal_version_id: 'v-1',
      chapter_no: directory[index].chapter_no,
      section_no: null,
      article_text: `第${articleNo}条正文。`,
      valid_from: '2024-01-01',
      valid_to: null,
      created_at: '2024-01-01T00:00:00Z',
    },
    previous_article_no: index > 0 ? directory[index - 1].article_no : null,
    next_article_no: index < directory.length - 1 ? directory[index + 1].article_no : null,
  }
}

const articleSegments: Synthesis = {
  article_version_id: 'av-1',
  text_segments: [
    { text: '公司应当设置', concept_id: null },
    { text: '董事会', concept_id: 'concept-board' },
    { text: '。', concept_id: null },
  ],
  generated_by: 'deterministic_template',
}

const ruleSynthesisNotAvailable = new ApiError(404, {
  code: 'RULE_SYNTHESIS_NOT_AVAILABLE',
  message: 'no PUBLISHED rule with a renderable requirement is bound to this article',
  trace_id: 'test-trace',
})

const ruleSynthesis: RuleSynthesis = {
  article_version_id: 'av-1',
  rule_id: 'rule-1',
  rule_code: 'RL-RULE-001',
  rule_name: '测试规则',
  text_segments: [
    { text: '本条对', concept_id: null },
    { text: '上市公司', concept_id: 'concept-listed-company' },
    { text: '设定义务性规范：不少于3人。（依据已发布规则 RL-RULE-001）', concept_id: null },
  ],
  generated_by: 'deterministic_rule_template',
}

function mockApi(options: { ruleSynthesisAvailable?: boolean } = {}) {
  vi.mocked(apiGet).mockImplementation((path: string) => {
    if (path === '/laws/RL-LAW/versions') return Promise.resolve(versions)
    if (path === '/laws/RL-LAW/versions/v1/articles') return Promise.resolve(directory)
    const navMatch = path.match(/^\/laws\/RL-LAW\/versions\/v1\/articles\/(.+)\/navigation$/)
    if (navMatch) return Promise.resolve(navFor(navMatch[1]))
    if (path.endsWith('/rule-synthesis')) {
      return options.ruleSynthesisAvailable
        ? Promise.resolve(ruleSynthesis)
        : Promise.reject(ruleSynthesisNotAvailable)
    }
    if (path.endsWith('/synthesis')) return Promise.resolve(articleSegments)
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

beforeEach(() => {
  vi.mocked(apiGet).mockReset()
})

async function mountAt(articleNo?: string) {
  await router.push({ name: 'article-reader', params: { lawCode: 'RL-LAW', versionName: 'v1', articleNo } })
  const wrapper = mount(ArticleReaderView, {
    props: { lawCode: 'RL-LAW', versionName: 'v1', articleNo },
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

describe('ArticleReaderView', () => {
  it('groups the directory by chapter and highlights the current article', async () => {
    mockApi()
    const wrapper = await mountAt('2')

    expect(wrapper.text()).toContain('第一章')
    expect(wrapper.text()).toContain('第二章')

    const active = wrapper.find('.article-link.active')
    expect(active.exists()).toBe(true)
    expect(active.text()).toContain('第2条')
  })

  it('disables the previous button at the first article and enables next', async () => {
    mockApi()
    const wrapper = await mountAt('1')

    const buttons = wrapper.findAll('.article-nav button')
    expect(buttons[0].attributes('disabled')).toBeDefined()
    expect(buttons[1].attributes('disabled')).toBeUndefined()
  })

  it('disables the next button at the last article and enables previous', async () => {
    mockApi()
    const wrapper = await mountAt('10')

    const buttons = wrapper.findAll('.article-nav button')
    expect(buttons[0].attributes('disabled')).toBeUndefined()
    expect(buttons[1].attributes('disabled')).toBeDefined()
  })

  it('navigates to the next article number when "下一条" is clicked', async () => {
    // Mounted directly (not via <router-view>), so a route change here
    // updates the router's current route but won't re-render this instance
    // with new props — that prop-from-route-param binding is <router-view>'s
    // job in the real app. This test only verifies the navigation intent.
    mockApi()
    const wrapper = await mountAt('1')

    await wrapper.findAll('.article-nav button')[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.params.articleNo).toBe('2')
  })

  it('renders the article body with inline concept links from the synthesis endpoint', async () => {
    // §6.3: core terms in the article text itself get lightweight links —
    // this is a different concern from the right-hand "小综合" panel.
    mockApi()
    const wrapper = await mountAt('1')

    const articleBody = wrapper.find('.article-text')
    expect(articleBody.text()).toContain('公司应当设置')
    expect(articleBody.find('button.concept-hyperlink').exists()).toBe(true)
    expect(articleBody.find('button.concept-hyperlink').text()).toBe('董事会')
  })

  it('shows the honest empty-synthesis copy when no rule is bound to the article', async () => {
    // Regression guard: a bound-but-unpublished or absent rule must not
    // fall back to echoing the article text disguised as a "小综合" — the
    // right panel should be an honest empty state instead.
    mockApi({ ruleSynthesisAvailable: false })
    const wrapper = await mountAt('1')

    expect(wrapper.text()).toContain('暂无经审核的综合内容')
    expect(wrapper.find('.synthesis-panel').exists()).toBe(false)
  })

  it('renders a genuine rule-derived synthesis in the right panel when available', async () => {
    mockApi({ ruleSynthesisAvailable: true })
    const wrapper = await mountAt('1')

    const panel = wrapper.find('.synthesis-panel')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('RL-RULE-001')
    expect(panel.find('button.concept-hyperlink').text()).toBe('上市公司')
  })

  it('redirects to the first real article when no article number is given', async () => {
    mockApi()
    await mountAt(undefined)

    expect(router.currentRoute.value.params.articleNo).toBe('1')
  })
})
