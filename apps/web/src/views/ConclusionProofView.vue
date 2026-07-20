<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { Proof, ProofStep } from '../types/api'

const props = defineProps<{
  conclusionId: string
}>()

const state = ref<RemoteState<Proof>>({ status: 'initial' })

async function load() {
  state.value = { status: 'loading' }
  try {
    const proof = await apiGet<Proof>(`/conclusions/${props.conclusionId}/proof`)
    state.value = { status: 'success', data: proof }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)

// The calculation payload is heterogeneous across rule handlers — this pulls
// out well-known reference keys (fact_id / fact_ids) wherever a step's
// calculation actually read a Fact, so the proof page can link to it without
// every handler needing a bespoke schema.
function factIdsIn(step: ProofStep): string[] {
  const calc = step.calculation as Record<string, unknown>
  const ids: string[] = []
  if (typeof calc.fact_id === 'string') ids.push(calc.fact_id)
  if (Array.isArray(calc.fact_ids)) {
    for (const id of calc.fact_ids) {
      if (typeof id === 'string') ids.push(id)
    }
  }
  return ids
}
</script>

<template>
  <div class="proof-view">
    <h1>证明链</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>

    <ol v-else-if="state.status === 'success'" class="step-list">
      <li v-for="step in state.data.steps" :key="step.sequence_no" class="step-card">
        <h3>第 {{ step.sequence_no }} 步：{{ step.step_type }}</h3>

        <p v-if="step.rule_id" class="drill-link">
          <RouterLink :to="{ name: 'rule-detail', params: { ruleId: step.rule_id } }">
            查看规则 {{ step.rule_code }} →
          </RouterLink>
        </p>
        <p v-if="factIdsIn(step).length" class="drill-link">
          <template v-for="factId in factIdsIn(step)" :key="factId">
            <RouterLink :to="{ name: 'fact-detail', params: { factId } }">查看事实 →</RouterLink>
          </template>
        </p>

        <div class="step-detail">
          <p v-if="Object.keys(step.input_facts).length">
            <strong>输入：</strong>{{ JSON.stringify(step.input_facts) }}
          </p>
          <p><strong>计算：</strong>{{ JSON.stringify(step.calculation) }}</p>
          <p v-if="Object.keys(step.output_state).length">
            <strong>输出：</strong>{{ JSON.stringify(step.output_state) }}
          </p>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.proof-view {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.step-list {
  padding-left: 20px;
}
.step-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.drill-link {
  font-size: 13px;
  margin: 4px 0;
  display: flex;
  gap: 12px;
}
.step-detail p {
  font-size: 13px;
  font-family: monospace;
  color: #444;
  word-break: break-all;
}
</style>
