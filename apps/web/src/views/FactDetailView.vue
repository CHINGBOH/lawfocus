<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { FactDetail, Subject } from '../types/api'

const props = defineProps<{
  factId: string
}>()

const state = ref<RemoteState<FactDetail>>({ status: 'initial' })
const subjectName = ref<string | null>(null)

async function load() {
  state.value = { status: 'loading' }
  try {
    const fact = await apiGet<FactDetail>(`/facts/${props.factId}`)
    state.value = { status: 'success', data: fact }
    const subject = await apiGet<Subject>(`/subjects/${fact.company_id}`)
    subjectName.value = subject.name
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)
</script>

<template>
  <div class="fact-detail-view">
    <h1>事实详情</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>

    <template v-else-if="state.status === 'success'">
      <section class="fact-card">
        <p>
          <strong>主体：</strong>
          <RouterLink :to="{ name: 'subject-facts', params: { subjectId: state.data.company_id } }">
            {{ subjectName ?? state.data.company_id }}
          </RouterLink>
        </p>
        <p><strong>事实类型：</strong>{{ state.data.fact_type }}</p>
        <p><strong>断言：</strong>{{ state.data.predicate }}</p>
        <p><strong>结构化值：</strong>{{ JSON.stringify(state.data.object_value) }}</p>
        <p>
          <strong>有效期间：</strong>{{ state.data.valid_from }} 起
          <template v-if="state.data.valid_to">至 {{ state.data.valid_to }}</template>
        </p>

        <h3>关联证据</h3>
        <p v-if="state.data.evidence.length === 0" class="empty-hint">暂无关联证据。</p>
        <ul v-else>
          <li v-for="link in state.data.evidence" :key="link.evidence.id">
            {{ link.evidence.title }}（{{ link.support_type }}）
            <span v-if="link.evidence.quote_text" class="quote">「{{ link.evidence.quote_text }}」</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.fact-detail-view {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.fact-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.quote {
  color: #666;
  font-style: italic;
}
.empty-hint {
  color: #999;
}
</style>
