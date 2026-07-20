<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { RemoteState } from '../types/remote'
import type { Evidence, Fact, FactDetail, Page } from '../types/api'

const props = defineProps<{
  subjectId: string
}>()

const auth = useAuthStore()

const factsState = ref<RemoteState<Fact[]>>({ status: 'initial' })
const expandedFactId = ref<string | null>(null)
const factDetailCache = ref<Record<string, FactDetail>>({})

const newFactType = ref('BOARD_COMPOSITION')
const newFactPredicate = ref('independent_director_count')
const newFactValueJson = ref('{"total": 9, "independent": 3}')
const newFactValidFrom = ref(new Date().toISOString().slice(0, 10))
const factFormError = ref<string | null>(null)
const factFormSubmitting = ref(false)

const newEvidenceTitle = ref('')
const newEvidenceType = ref('AnnualReport')
const newEvidenceQuote = ref('')
const evidenceFormError = ref<string | null>(null)
const evidenceFormSubmitting = ref(false)
const lastCreatedEvidenceId = ref<string | null>(null)

async function loadFacts() {
  if (!auth.currentTenantId) {
    factsState.value = { status: 'error', message: '当前账号没有租户范围授权，无法查看事实' }
    return
  }
  factsState.value = { status: 'loading' }
  try {
    const page = await apiGet<Page<Fact>>(
      `/facts?tenant_id=${auth.currentTenantId}&subject_id=${props.subjectId}`,
    )
    factsState.value = page.items.length === 0 ? { status: 'empty' } : { status: 'success', data: page.items }
  } catch (err) {
    factsState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

async function toggleFactDetail(factId: string) {
  if (expandedFactId.value === factId) {
    expandedFactId.value = null
    return
  }
  expandedFactId.value = factId
  if (!factDetailCache.value[factId]) {
    factDetailCache.value[factId] = await apiGet<FactDetail>(`/facts/${factId}`)
  }
}

async function createFact() {
  factFormError.value = null
  let objectValue: Record<string, unknown>
  try {
    objectValue = JSON.parse(newFactValueJson.value)
  } catch {
    factFormError.value = '结构化值必须是合法 JSON'
    return
  }
  if (!auth.currentTenantId) {
    factFormError.value = '当前账号没有租户范围授权'
    return
  }

  factFormSubmitting.value = true
  try {
    await apiPost<Fact>('/facts', {
      tenant_id: auth.currentTenantId,
      company_id: props.subjectId,
      fact_type: newFactType.value,
      predicate: newFactPredicate.value,
      object_value: objectValue,
      valid_from: newFactValidFrom.value,
    })
    await loadFacts()
  } catch (err) {
    factFormError.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    factFormSubmitting.value = false
  }
}

async function createEvidence() {
  evidenceFormError.value = null
  if (!auth.currentTenantId) {
    evidenceFormError.value = '当前账号没有租户范围授权'
    return
  }
  evidenceFormSubmitting.value = true
  try {
    const evidence = await apiPost<Evidence>('/evidence', {
      tenant_id: auth.currentTenantId,
      evidence_type: newEvidenceType.value,
      title: newEvidenceTitle.value,
      quote_text: newEvidenceQuote.value || null,
    })
    lastCreatedEvidenceId.value = evidence.id
  } catch (err) {
    evidenceFormError.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    evidenceFormSubmitting.value = false
  }
}

async function linkToFact(factId: string) {
  if (!lastCreatedEvidenceId.value) return
  await apiPost(`/facts/${factId}/evidence/${lastCreatedEvidenceId.value}`, { support_type: 'DIRECT' })
  delete factDetailCache.value[factId]
  await toggleFactDetail(factId)
  await toggleFactDetail(factId)
}

onMounted(loadFacts)
</script>

<template>
  <div class="fact-evidence-view">
    <h1>事实与证据</h1>

    <section class="fact-list-section">
      <h2>已录入事实</h2>
      <p v-if="factsState.status === 'initial' || factsState.status === 'loading'">加载中…</p>
      <p v-else-if="factsState.status === 'error'">
        加载失败：{{ factsState.message }}
        <button @click="loadFacts">重试</button>
      </p>
      <p v-else-if="factsState.status === 'empty'">暂无事实记录。</p>

      <ul v-else class="fact-list">
        <li v-for="fact in factsState.data" :key="fact.id" class="fact-item">
          <button type="button" class="fact-summary" @click="toggleFactDetail(fact.id)">
            {{ fact.fact_type }} · {{ fact.predicate }} = {{ JSON.stringify(fact.object_value) }}
            <span class="fact-validity">
              （{{ fact.valid_from }} 起<template v-if="fact.valid_to">至 {{ fact.valid_to }}</template>）
            </span>
          </button>

          <div v-if="expandedFactId === fact.id && factDetailCache[fact.id]" class="fact-detail">
            <h4>证据（{{ factDetailCache[fact.id].evidence.length }}）</h4>
            <ul v-if="factDetailCache[fact.id].evidence.length">
              <li v-for="link in factDetailCache[fact.id].evidence" :key="link.evidence.id">
                {{ link.evidence.title }}（{{ link.support_type }}）
                <span v-if="link.evidence.quote_text" class="quote">「{{ link.evidence.quote_text }}」</span>
              </li>
            </ul>
            <p v-else class="empty-hint">该事实暂无关联证据。</p>
            <button
              v-if="lastCreatedEvidenceId"
              type="button"
              class="link-btn"
              @click="linkToFact(fact.id)"
            >
              关联刚创建的证据 →
            </button>
          </div>
        </li>
      </ul>
    </section>

    <section class="form-section">
      <h2>录入事实</h2>
      <form @submit.prevent="createFact">
        <label>
          事实类型
          <input v-model="newFactType" required />
        </label>
        <label>
          断言（predicate）
          <input v-model="newFactPredicate" required />
        </label>
        <label>
          结构化值（JSON）
          <textarea v-model="newFactValueJson" rows="2" required />
        </label>
        <label>
          生效日期
          <input v-model="newFactValidFrom" type="date" required />
        </label>
        <button :disabled="factFormSubmitting" type="submit">
          {{ factFormSubmitting ? '提交中…' : '创建事实' }}
        </button>
        <p v-if="factFormError" class="error" role="alert">{{ factFormError }}</p>
      </form>
    </section>

    <section class="form-section">
      <h2>录入证据元数据</h2>
      <p class="hint">MVP 不上传真实文件正文，仅保存证据元数据（来源、引用文本等）。</p>
      <form @submit.prevent="createEvidence">
        <label>
          证据类型
          <input v-model="newEvidenceType" required />
        </label>
        <label>
          标题
          <input v-model="newEvidenceTitle" required />
        </label>
        <label>
          引用文本
          <textarea v-model="newEvidenceQuote" rows="2" />
        </label>
        <button :disabled="evidenceFormSubmitting" type="submit">
          {{ evidenceFormSubmitting ? '提交中…' : '创建证据' }}
        </button>
        <p v-if="evidenceFormError" class="error" role="alert">{{ evidenceFormError }}</p>
        <p v-if="lastCreatedEvidenceId" class="success-hint">
          证据已创建，可在上方事实列表中展开并点击"关联刚创建的证据"。
        </p>
      </form>
    </section>
  </div>
</template>

<style scoped>
.fact-evidence-view {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.fact-list-section,
.form-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.fact-list {
  list-style: none;
  padding: 0;
}
.fact-item {
  border-top: 1px solid #eee;
  padding: 8px 0;
}
.fact-summary {
  background: none;
  border: none;
  text-align: left;
  width: 100%;
  cursor: pointer;
  font: inherit;
  padding: 4px 0;
}
.fact-validity {
  color: #888;
  font-size: 12px;
}
.fact-detail {
  padding: 8px 0 8px 16px;
  font-size: 14px;
}
.quote {
  color: #666;
  font-style: italic;
}
.empty-hint {
  color: #999;
}
form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}
input,
textarea {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-family: inherit;
}
button {
  align-self: flex-start;
  padding: 8px 16px;
  background: #1f2d3d;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
}
.link-btn {
  margin-top: 8px;
  background: #1a5fb4;
}
.error {
  color: #c0392b;
  font-size: 13px;
}
.success-hint {
  color: #15803d;
  font-size: 13px;
}
.hint {
  color: #888;
  font-size: 12px;
}
</style>
