<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { apiGet, apiPost, ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { RemoteState } from '../types/remote'
import type { RuleDetail, RuleVersionSummary } from '../types/api'

const props = defineProps<{
  ruleId: string
}>()

const auth = useAuthStore()
const state = ref<RemoteState<RuleDetail>>({ status: 'initial' })
const actionError = ref<string | null>(null)
const actionSubmitting = ref(false)

const reviewDecision = ref<'APPROVED' | 'CHANGES_REQUESTED'>('APPROVED')
const reviewComment = ref('')

async function load() {
  state.value = { status: 'loading' }
  try {
    const rule = await apiGet<RuleDetail>(`/rules/${props.ruleId}`)
    state.value = { status: 'success', data: rule }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)

const status = computed(() => (state.value.status === 'success' ? state.value.data.latest_version?.status : null))

const canSubmit = computed(
  () =>
    auth.roleCodes.some((r) => r === 'KNOWLEDGE_EDITOR' || r === 'SYSTEM_ADMIN') &&
    (status.value === 'DRAFT' || status.value === 'CHANGES_REQUESTED'),
)
const submitDisabledReason = computed(() => {
  if (!auth.roleCodes.some((r) => r === 'KNOWLEDGE_EDITOR' || r === 'SYSTEM_ADMIN')) return '当前账号没有 KnowledgeEditor 权限'
  if (!(status.value === 'DRAFT' || status.value === 'CHANGES_REQUESTED')) return `当前状态为 ${status.value}，不可提交`
  return null
})

const canLegalReview = computed(
  () => auth.roleCodes.some((r) => r === 'LEGAL_REVIEWER' || r === 'SYSTEM_ADMIN') && status.value === 'IN_REVIEW',
)
const legalReviewDisabledReason = computed(() => {
  if (!auth.roleCodes.some((r) => r === 'LEGAL_REVIEWER' || r === 'SYSTEM_ADMIN')) return '当前账号没有 LegalReviewer 权限'
  if (status.value !== 'IN_REVIEW') return `当前状态为 ${status.value}，不在法律审核阶段`
  return null
})

const canTechReview = computed(
  () =>
    auth.roleCodes.some((r) => r === 'TECHNICAL_REVIEWER' || r === 'SYSTEM_ADMIN') &&
    status.value === 'LEGAL_APPROVED',
)
const techReviewDisabledReason = computed(() => {
  if (!auth.roleCodes.some((r) => r === 'TECHNICAL_REVIEWER' || r === 'SYSTEM_ADMIN'))
    return '当前账号没有 TechnicalReviewer 权限'
  if (status.value !== 'LEGAL_APPROVED') return `当前状态为 ${status.value}，需处于 LEGAL_APPROVED 才能技术审核`
  return null
})

const canPublish = computed(
  () => auth.roleCodes.some((r) => r === 'PUBLISHER' || r === 'SYSTEM_ADMIN') && status.value === 'TECH_APPROVED',
)
const publishDisabledReason = computed(() => {
  if (!auth.roleCodes.some((r) => r === 'PUBLISHER' || r === 'SYSTEM_ADMIN')) return '当前账号没有 Publisher 权限'
  if (status.value !== 'TECH_APPROVED') return `当前状态为 ${status.value}，需处于 TECH_APPROVED 才能发布`
  return null
})

async function submitRule() {
  actionSubmitting.value = true
  actionError.value = null
  try {
    await apiPost<RuleVersionSummary>(`/rules/${props.ruleId}/submit`, {})
    await load()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : '提交失败'
  } finally {
    actionSubmitting.value = false
  }
}

async function submitReview(reviewType: 'LEGAL' | 'TECHNICAL') {
  if (reviewDecision.value === 'CHANGES_REQUESTED' && !reviewComment.value.trim()) {
    actionError.value = '退回时必须填写审核意见'
    return
  }
  actionSubmitting.value = true
  actionError.value = null
  try {
    await apiPost(`/rules/${props.ruleId}/reviews`, {
      review_type: reviewType,
      decision: reviewDecision.value,
      comment: reviewComment.value || null,
    })
    reviewComment.value = ''
    await load()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : '提交审核失败'
  } finally {
    actionSubmitting.value = false
  }
}

async function publishRule() {
  actionSubmitting.value = true
  actionError.value = null
  try {
    await apiPost<RuleVersionSummary>(`/rules/${props.ruleId}/publish`, {})
    await load()
  } catch (err) {
    if (err instanceof ApiError && err.code === 'PUBLISH_GATE_FAILED') {
      actionError.value = `发布门禁未通过：${err.message}`
    } else {
      actionError.value = err instanceof Error ? err.message : '发布失败'
    }
  } finally {
    actionSubmitting.value = false
  }
}
</script>

<template>
  <div class="rule-detail">
    <h1>规则详情</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>

    <template v-else-if="state.status === 'success'">
      <section class="rule-card">
        <h2>{{ state.data.name }}（{{ state.data.code }}）</h2>

        <template v-if="state.data.latest_version">
          <p><strong>状态：</strong>{{ state.data.latest_version.status }}</p>
          <p><strong>模态：</strong>{{ state.data.latest_version.modality }}</p>
          <p>
            <strong>有效期：</strong>{{ state.data.latest_version.effective_from ?? '未设定' }} 起
            <template v-if="state.data.latest_version.effective_to">
              至 {{ state.data.latest_version.effective_to }}
            </template>
          </p>

          <h3>法源</h3>
          <p v-if="state.data.latest_version.sources.length === 0" class="empty-hint">暂无绑定法源。</p>
          <ul v-else class="source-list">
            <li v-for="(source, idx) in state.data.latest_version.sources" :key="idx">
              {{ source.article_version.chapter_no }}（{{ source.relation_type }}）
              <p class="article-text">{{ source.article_version.article_text }}</p>
            </li>
          </ul>

          <h3>测试案例（{{ state.data.latest_version.test_cases.length }}）</h3>
          <p v-if="state.data.latest_version.test_cases.length === 0" class="empty-hint">暂无测试案例。</p>
          <table v-else class="test-case-table">
            <thead>
              <tr>
                <th>类别</th>
                <th>期望结果</th>
                <th>豁免理由</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="tc in state.data.latest_version.test_cases" :key="tc.id">
                <td>{{ tc.case_type }}</td>
                <td>{{ tc.expected_status }}</td>
                <td>{{ tc.not_applicable_reason ?? '—' }}</td>
              </tr>
            </tbody>
          </table>

          <h3>审核记录（{{ state.data.latest_version.review_decisions.length }}）</h3>
          <p v-if="state.data.latest_version.review_decisions.length === 0" class="empty-hint">暂无审核记录。</p>
          <ul v-else class="review-list">
            <li v-for="review in state.data.latest_version.review_decisions" :key="review.id">
              [{{ review.review_type }}] {{ review.reviewer_display_name }}：{{ review.decision }}
              <span v-if="review.comment" class="review-comment">「{{ review.comment }}」</span>
              <span class="review-time">{{ review.created_at }}</span>
            </li>
          </ul>

          <h3>操作</h3>
          <div class="actions">
            <div class="action-row">
              <button :disabled="!canSubmit || actionSubmitting" @click="submitRule">提交审核</button>
              <span v-if="submitDisabledReason" class="disabled-reason">{{ submitDisabledReason }}</span>
            </div>

            <div class="action-row review-row">
              <select v-model="reviewDecision">
                <option value="APPROVED">通过</option>
                <option value="CHANGES_REQUESTED">退回</option>
              </select>
              <input v-model="reviewComment" placeholder="审核意见（退回时必填）" />
              <button :disabled="!canLegalReview || actionSubmitting" @click="submitReview('LEGAL')">
                法律审核
              </button>
              <span v-if="legalReviewDisabledReason" class="disabled-reason">{{ legalReviewDisabledReason }}</span>
            </div>

            <div class="action-row review-row">
              <button :disabled="!canTechReview || actionSubmitting" @click="submitReview('TECHNICAL')">
                技术审核
              </button>
              <span v-if="techReviewDisabledReason" class="disabled-reason">{{ techReviewDisabledReason }}</span>
            </div>

            <div class="action-row">
              <button :disabled="!canPublish || actionSubmitting" @click="publishRule">发布</button>
              <span v-if="publishDisabledReason" class="disabled-reason">{{ publishDisabledReason }}</span>
            </div>
          </div>
          <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
        </template>
        <p v-else class="empty-hint">该规则暂无版本。</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.rule-detail {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.rule-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.source-list,
.review-list {
  list-style: none;
  padding: 0;
}
.source-list li,
.review-list li {
  border-top: 1px solid #eee;
  padding: 8px 0;
  font-size: 14px;
}
.article-text {
  color: #555;
  font-size: 14px;
}
.test-case-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.test-case-table th,
.test-case-table td {
  text-align: left;
  padding: 4px 8px;
  border-bottom: 1px solid #eee;
}
.review-comment {
  color: #666;
  font-style: italic;
}
.review-time {
  color: #999;
  font-size: 12px;
  margin-left: 8px;
}
.empty-hint {
  color: #999;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.review-row select,
.review-row input {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 8px 16px;
  background: #1f2d3d;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.disabled-reason {
  color: #999;
  font-size: 12px;
}
.error {
  color: #c0392b;
  font-size: 13px;
}
</style>
