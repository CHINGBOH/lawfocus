<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { Page, Subject } from '../types/api'

const state = ref<RemoteState<Subject[]>>({ status: 'initial' })

async function load() {
  state.value = { status: 'loading' }
  try {
    // This page is titled "上市公司" — only list listed companies, not the
    // individual persons (directors etc.) that also live in legal_subject.
    const page = await apiGet<Page<Subject>>('/subjects?subject_type=LISTED_COMPANY&page_size=100')
    state.value = page.items.length === 0 ? { status: 'empty' } : { status: 'success', data: page.items }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)
</script>

<template>
  <div class="subject-list">
    <h1>上市公司</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>
    <p v-else-if="state.status === 'empty'">暂无已收录主体。</p>

    <ul v-else class="subject-cards">
      <li v-for="subject in state.data" :key="subject.id" class="subject-card">
        <h2>{{ subject.name }}</h2>
        <p class="subject-meta">
          {{ subject.subject_type }}
          <template v-if="subject.listed"> · 已上市 · {{ subject.exchange }}</template>
        </p>
        <div class="subject-links">
          <RouterLink :to="{ name: 'subject-governance', params: { subjectId: subject.id } }">
            治理结构 →
          </RouterLink>
          <RouterLink :to="{ name: 'subject-facts', params: { subjectId: subject.id } }">
            事实与证据 →
          </RouterLink>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.subject-list {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.subject-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.subject-meta {
  color: #888;
  font-size: 13px;
}
.subject-links {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}
</style>
