<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { RuleOut } from '../types/api'

const state = ref<RemoteState<RuleOut[]>>({ status: 'initial' })

async function load() {
  state.value = { status: 'loading' }
  try {
    const rules = await apiGet<RuleOut[]>('/rules')
    state.value = rules.length === 0 ? { status: 'empty' } : { status: 'success', data: rules }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)
</script>

<template>
  <div class="rule-list">
    <h1>规则中心</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>
    <p v-else-if="state.status === 'empty'">暂无规则。</p>

    <ul v-else class="rule-cards">
      <li v-for="rule in state.data" :key="rule.id" class="rule-card">
        <RouterLink :to="{ name: 'rule-detail', params: { ruleId: rule.id } }">
          <h2>{{ rule.name }}（{{ rule.code }}）</h2>
        </RouterLink>
        <p class="rule-status">状态：{{ rule.latest_version?.status ?? '无版本' }}</p>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.rule-list {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.rule-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.rule-card a {
  color: #1a5fb4;
  text-decoration: none;
}
.rule-card h2 {
  margin: 0 0 4px;
}
.rule-status {
  color: #888;
  font-size: 13px;
}
</style>
