<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { Law } from '../types/api'

const state = ref<RemoteState<Law[]>>({ status: 'initial' })

async function load() {
  state.value = { status: 'loading' }
  try {
    const laws = await apiGet<Law[]>('/laws')
    state.value = laws.length === 0 ? { status: 'empty' } : { status: 'success', data: laws }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(load)
</script>

<template>
  <div class="law-list">
    <h1>法律仓库</h1>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>
    <p v-else-if="state.status === 'empty'">暂无已收录法律。</p>

    <ul v-else class="law-cards">
      <li v-for="law in state.data" :key="law.id" class="law-card">
        <h2>{{ law.name }}</h2>
        <p class="law-meta">{{ law.code }} · {{ law.document_type }} · {{ law.jurisdiction }}</p>
        <ul class="version-list">
          <li v-for="version in law.versions" :key="version.id">
            <span class="version-name">{{ version.version_name }}</span>
            <span class="version-status">[{{ version.status }}]</span>
            <span class="version-range">
              {{ version.effective_from }} 起
              <template v-if="version.effective_to">至 {{ version.effective_to }}</template>
            </span>
            <RouterLink
              :to="{
                name: 'article-reader',
                params: { lawCode: law.code, versionName: version.version_name },
              }"
            >
              打开目录 →
            </RouterLink>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.law-list {
  padding: 24px;
  max-width: 800px;
  margin: 0 auto;
}
.law-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.law-meta {
  color: #888;
  font-size: 13px;
}
.version-list {
  list-style: none;
  padding: 0;
}
.version-list li {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border-top: 1px solid #eee;
}
.version-status {
  color: #999;
  font-size: 12px;
}
.version-range {
  color: #666;
  font-size: 12px;
}
</style>
