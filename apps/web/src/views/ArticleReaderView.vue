<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, apiGet } from '../api/client'
import ConceptHyperlink from '../components/ConceptHyperlink.vue'
import LegalSynthesisPanel from '../components/LegalSynthesisPanel.vue'
import type { RemoteState } from '../types/remote'
import type {
  ArticleNavigation,
  ArticleSummary,
  ArticleVersion,
  LegalVersion,
  RuleSynthesis,
  Synthesis,
} from '../types/api'

const props = defineProps<{
  lawCode: string
  versionName: string
  articleNo?: string
}>()

const router = useRouter()

const versionsState = ref<RemoteState<LegalVersion[]>>({ status: 'initial' })
const directoryState = ref<RemoteState<ArticleSummary[]>>({ status: 'initial' })
const articleState = ref<RemoteState<ArticleVersion>>({ status: 'initial' })
// Concept-tagged rendering of the article body itself (§6.3 "核心名词以轻量
// 链接样式显示") — distinct from the right-hand "小综合", which is a real
// synthesis assembled from a bound rule's structured fields, not an echo of
// the article text.
const articleSegmentsState = ref<RemoteState<Synthesis>>({ status: 'initial' })
const ruleSynthesisState = ref<RemoteState<RuleSynthesis>>({ status: 'initial' })
const previousArticleNo = ref<string | null>(null)
const nextArticleNo = ref<string | null>(null)

const currentVersionMeta = computed(() => {
  if (versionsState.value.status !== 'success') return undefined
  return versionsState.value.data.find((v) => v.version_name === props.versionName)
})

const chapterGroups = computed(() => {
  if (directoryState.value.status !== 'success') return []
  const groups = new Map<string, ArticleSummary[]>()
  for (const item of directoryState.value.data) {
    const key = item.chapter_no ?? '（无章节标注）'
    const bucket = groups.get(key)
    if (bucket) {
      bucket.push(item)
    } else {
      groups.set(key, [item])
    }
  }
  return Array.from(groups.entries()).map(([chapter, articles]) => ({ chapter, articles }))
})

function goToArticle(articleNo: string | null) {
  if (!articleNo) return
  router.push({
    name: 'article-reader',
    params: { lawCode: props.lawCode, versionName: props.versionName, articleNo },
  })
}

function onVersionChange(event: Event) {
  const versionName = (event.target as HTMLSelectElement).value
  router.push({
    name: 'article-reader',
    params: { lawCode: props.lawCode, versionName, articleNo: props.articleNo },
  })
}

async function loadVersions() {
  versionsState.value = { status: 'loading' }
  try {
    const versions = await apiGet<LegalVersion[]>(`/laws/${props.lawCode}/versions`)
    versionsState.value = versions.length === 0 ? { status: 'empty' } : { status: 'success', data: versions }
  } catch (err) {
    versionsState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

async function loadDirectory() {
  directoryState.value = { status: 'loading' }
  try {
    const directory = await apiGet<ArticleSummary[]>(
      `/laws/${props.lawCode}/versions/${props.versionName}/articles`,
    )
    directoryState.value = directory.length === 0 ? { status: 'empty' } : { status: 'success', data: directory }
    // The law list links into "the directory" without an article number —
    // open the first real article rather than guessing or defaulting to a
    // fixed demo article.
    if (!props.articleNo && directory.length > 0) {
      router.replace({
        name: 'article-reader',
        params: { lawCode: props.lawCode, versionName: props.versionName, articleNo: directory[0].article_no },
      })
    }
  } catch (err) {
    directoryState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

async function loadArticle() {
  if (!props.articleNo) return
  articleState.value = { status: 'loading' }
  articleSegmentsState.value = { status: 'loading' }
  ruleSynthesisState.value = { status: 'loading' }
  try {
    const nav = await apiGet<ArticleNavigation>(
      `/laws/${props.lawCode}/versions/${props.versionName}/articles/${props.articleNo}/navigation`,
    )
    articleState.value = { status: 'success', data: nav.current }
    previousArticleNo.value = nav.previous_article_no
    nextArticleNo.value = nav.next_article_no
  } catch (err) {
    const message = err instanceof Error ? err.message : '加载失败'
    articleState.value = { status: 'error', message }
    articleSegmentsState.value = { status: 'error', message }
    ruleSynthesisState.value = { status: 'error', message }
    return
  }

  const articleVersionId = articleState.value.status === 'success' ? articleState.value.data.id : null
  if (!articleVersionId) return

  try {
    const segments = await apiGet<Synthesis>(`/articles/${articleVersionId}/synthesis`)
    articleSegmentsState.value = { status: 'success', data: segments }
  } catch (err) {
    // Non-fatal — the article body still renders as plain text below.
    articleSegmentsState.value = {
      status: 'error',
      message: err instanceof Error ? err.message : '加载失败',
    }
  }

  try {
    const ruleSynthesis = await apiGet<RuleSynthesis>(`/articles/${articleVersionId}/rule-synthesis`)
    ruleSynthesisState.value = { status: 'success', data: ruleSynthesis }
  } catch (err) {
    if (err instanceof ApiError && err.code === 'RULE_SYNTHESIS_NOT_AVAILABLE') {
      ruleSynthesisState.value = { status: 'empty' }
    } else {
      ruleSynthesisState.value = {
        status: 'error',
        message: err instanceof Error ? err.message : '加载失败',
      }
    }
  }
}

onMounted(() => {
  loadVersions()
  loadDirectory()
  loadArticle()
})
watch(
  () => [props.lawCode, props.versionName],
  () => {
    loadVersions()
    loadDirectory()
  },
)
watch(() => props.articleNo, loadArticle)
</script>

<template>
  <div class="article-reader">
    <aside class="reader-directory">
      <h3>法律目录</h3>
      <p class="law-code">{{ lawCode }}</p>

      <p v-if="versionsState.status === 'loading' || versionsState.status === 'initial'">版本加载中…</p>
      <p v-else-if="versionsState.status === 'error'">版本加载失败：{{ versionsState.message }}</p>
      <template v-else-if="versionsState.status === 'success'">
        <select class="version-select" :value="versionName" @change="onVersionChange">
          <option v-for="v in versionsState.data" :key="v.id" :value="v.version_name">
            {{ v.version_name }}（{{ v.status }}）
          </option>
        </select>
        <p v-if="currentVersionMeta" class="version-effective">
          {{ currentVersionMeta.effective_from }} 起
          <template v-if="currentVersionMeta.effective_to">至 {{ currentVersionMeta.effective_to }}</template>
        </p>
      </template>

      <p v-if="directoryState.status === 'loading' || directoryState.status === 'initial'">目录加载中…</p>
      <p v-else-if="directoryState.status === 'error'">
        目录加载失败：{{ directoryState.message }}
        <button @click="loadDirectory">重试</button>
      </p>
      <p v-else-if="directoryState.status === 'empty'">该版本暂无条文。</p>
      <nav v-else-if="directoryState.status === 'success'" class="directory-tree">
        <div v-for="group in chapterGroups" :key="group.chapter" class="chapter-group">
          <h4>{{ group.chapter }}</h4>
          <ul>
            <li v-for="item in group.articles" :key="item.article_no">
              <RouterLink
                class="article-link"
                :class="{ active: item.article_no === articleNo }"
                :to="{
                  name: 'article-reader',
                  params: { lawCode, versionName, articleNo: item.article_no },
                }"
                :title="item.summary"
              >
                第{{ item.article_no }}条
              </RouterLink>
            </li>
          </ul>
        </div>
      </nav>
    </aside>

    <section class="reader-article">
      <p v-if="articleState.status === 'initial' || articleState.status === 'loading'">加载中…</p>
      <p v-else-if="articleState.status === 'error'">
        加载失败：{{ articleState.message }}
        <button @click="loadArticle">重试</button>
      </p>
      <template v-else-if="articleState.status === 'success'">
        <nav class="article-nav">
          <button :disabled="!previousArticleNo" @click="goToArticle(previousArticleNo)">← 上一条</button>
          <span class="article-position">第{{ articleState.data.article_no }}条</span>
          <button :disabled="!nextArticleNo" @click="goToArticle(nextArticleNo)">下一条 →</button>
        </nav>
        <p class="article-meta">
          {{ articleState.data.chapter_no }} · 生效于 {{ articleState.data.valid_from }}
          <template v-if="articleState.data.valid_to">至 {{ articleState.data.valid_to }}</template>
        </p>
        <!-- Core terms rendered with lightweight concept links per §6.3.
             Falls back to plain text if the concept-tagging call itself
             fails — that's a secondary enhancement, not the primary read. -->
        <p class="article-text">
          <template v-if="articleSegmentsState.status === 'success'">
            <template v-for="(segment, idx) in articleSegmentsState.data.text_segments" :key="idx">
              <ConceptHyperlink
                v-if="segment.concept_id"
                :concept-id="segment.concept_id"
                :text="segment.text"
              />
              <template v-else>{{ segment.text }}</template>
            </template>
          </template>
          <template v-else>{{ articleState.data.article_text }}</template>
        </p>
      </template>
    </section>

    <aside class="reader-synthesis">
      <p v-if="ruleSynthesisState.status === 'initial' || ruleSynthesisState.status === 'loading'">加载中…</p>
      <p v-else-if="ruleSynthesisState.status === 'error'">加载失败：{{ ruleSynthesisState.message }}</p>
      <p v-else-if="ruleSynthesisState.status === 'empty'">暂无经审核的综合内容。</p>
      <LegalSynthesisPanel
        v-else-if="ruleSynthesisState.status === 'success'"
        :synthesis="ruleSynthesisState.data"
      />
    </aside>
  </div>
</template>

<style scoped>
.article-reader {
  display: grid;
  grid-template-columns: 20% 50% 30%;
  height: 100%;
}
.reader-directory {
  background: #fff;
  border-right: 1px solid #eee;
  padding: 20px;
  overflow-y: auto;
}
.version-select {
  width: 100%;
  margin: 8px 0 4px;
}
.version-effective {
  color: #888;
  font-size: 12px;
  margin-bottom: 12px;
}
.directory-tree {
  margin-top: 12px;
}
.chapter-group h4 {
  font-size: 13px;
  color: #666;
  margin: 12px 0 4px;
}
.chapter-group ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.article-link {
  display: block;
  padding: 4px 6px;
  font-size: 13px;
  border-radius: 4px;
  color: #333;
  text-decoration: none;
}
.article-link:hover {
  background: #f2f2f2;
}
.article-link.active {
  background: #e6f0ff;
  color: #1a56db;
  font-weight: 600;
}
.reader-article {
  padding: 24px 32px;
  overflow-y: auto;
}
.article-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.article-position {
  font-weight: 600;
  color: #555;
}
.article-meta {
  color: #888;
  font-size: 13px;
}
.article-text {
  font-size: 16px;
  line-height: 2;
}
@media (max-width: 900px) {
  .article-reader {
    grid-template-columns: 1fr;
  }
}
</style>
