<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { ComplianceCheck, Subject } from '../types/api'

const props = defineProps<{
  checkId: string
}>()

const state = ref<RemoteState<ComplianceCheck>>({ status: 'initial' })
const subjectName = ref<string | null>(null)

const RESULT_LABELS: Record<string, { label: string; nextStep: string; className: string }> = {
  TRUE: { label: '符合', nextStep: '查看依据', className: 'result-true' },
  FALSE: { label: '不符合', nextStep: '查看差距与整改提示', className: 'result-false' },
  UNKNOWN: { label: '资料不足', nextStep: '跳转补充事实', className: 'result-unknown' },
  CONFLICT: { label: '事实或规则冲突', nextStep: '查看冲突来源', className: 'result-conflict' },
  NOT_APPLICABLE: { label: '不适用', nextStep: '查看排除原因', className: 'result-na' },
}

async function load() {
  state.value = { status: 'loading' }
  try {
    const check = await apiGet<ComplianceCheck>(`/compliance-checks/${props.checkId}`)
    state.value = { status: 'success', data: check }
    const subject = await apiGet<Subject>(`/subjects/${check.subject_id}`)
    subjectName.value = subject.name
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)
</script>

<template>
  <div class="result-view">
    <h1>合规检查结果</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>

    <template v-else-if="state.status === 'success'">
      <section class="summary-card">
        <p><strong>主体：</strong>{{ subjectName ?? state.data.subject_id }}</p>
        <p><strong>评价时点：</strong>{{ state.data.evaluation_time }}</p>
        <p><strong>状态：</strong>{{ state.data.status }}</p>
        <p v-if="state.data.deprecations.length" class="deprecation-hint">
          注意：本次请求使用了已弃用字段（{{ state.data.deprecations.join('；') }}）
        </p>
      </section>

      <p class="disclaimer">
        以下按规则逐条展示五值结论，不汇总为单一合规分数——五种状态含义不同，需分别处理。
      </p>

      <ul class="conclusion-list">
        <li
          v-for="conclusion in state.data.conclusions"
          :key="conclusion.id"
          class="conclusion-card"
          :class="RESULT_LABELS[conclusion.result_status]?.className"
        >
          <h3>{{ conclusion.rule_name }}（{{ conclusion.rule_code }}）</h3>
          <p class="result-badge">
            {{ RESULT_LABELS[conclusion.result_status]?.label ?? conclusion.result_status }}
          </p>

          <p v-if="conclusion.applicable_reason" class="reason">{{ conclusion.applicable_reason }}</p>
          <p v-if="conclusion.excluded_reason" class="reason">排除原因：{{ conclusion.excluded_reason }}</p>
          <p v-if="conclusion.missing_facts.length" class="reason">
            缺失事实：{{ conclusion.missing_facts.join('、') }}
          </p>

          <div class="next-step">
            <RouterLink
              v-if="conclusion.result_status === 'UNKNOWN'"
              :to="{ name: 'subject-facts', params: { subjectId: state.data.subject_id } }"
            >
              {{ RESULT_LABELS.UNKNOWN.nextStep }} →
            </RouterLink>
            <RouterLink v-else :to="{ name: 'conclusion-proof', params: { conclusionId: conclusion.id } }">
              {{ RESULT_LABELS[conclusion.result_status]?.nextStep ?? '查看详情' }} →
            </RouterLink>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.result-view {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.summary-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.disclaimer {
  color: #888;
  font-size: 13px;
  margin-bottom: 16px;
}
.deprecation-hint {
  color: #b45309;
  font-size: 12px;
}
.conclusion-list {
  list-style: none;
  padding: 0;
}
.conclusion-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  border-left: 4px solid #ccc;
}
.conclusion-card.result-true {
  border-left-color: #15803d;
}
.conclusion-card.result-false {
  border-left-color: #b91c1c;
}
.conclusion-card.result-unknown {
  border-left-color: #b45309;
}
.conclusion-card.result-conflict {
  border-left-color: #7c3aed;
}
.conclusion-card.result-na {
  border-left-color: #6b7280;
}
.result-badge {
  font-weight: 600;
  font-size: 15px;
}
.reason {
  color: #555;
  font-size: 13px;
}
.next-step {
  margin-top: 8px;
}
.error {
  color: #c0392b;
}
</style>
