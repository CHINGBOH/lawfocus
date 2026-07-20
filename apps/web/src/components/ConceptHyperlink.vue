<script setup lang="ts">
import { ref } from 'vue'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { ConceptDetail } from '../types/api'

const props = defineProps<{
  conceptId: string
  text: string
}>()

const open = ref(false)
const state = ref<RemoteState<ConceptDetail>>({ status: 'initial' })

async function toggle() {
  open.value = !open.value
  if (open.value && state.value.status !== 'success') {
    state.value = { status: 'loading' }
    try {
      const detail = await apiGet<ConceptDetail>(`/concepts/${props.conceptId}`)
      state.value = { status: 'success', data: detail }
    } catch (err) {
      state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
    }
  }
}
</script>

<template>
  <span class="concept-hyperlink-wrapper">
    <button type="button" class="concept-hyperlink" @click="toggle">{{ text }}</button>
    <div v-if="open" class="concept-popover" role="dialog">
      <p v-if="state.status === 'loading'">加载中…</p>
      <p v-else-if="state.status === 'error'">加载失败：{{ state.message }}</p>
      <template v-else-if="state.status === 'success'">
        <h4>{{ state.data.name }} <span class="review-badge">{{ state.data.review_status }}</span></h4>
        <p class="definition">{{ state.data.definition }}</p>
        <div v-if="state.data.sources.length" class="sources">
          <strong>定义来源：</strong>
          <ul>
            <li v-for="(source, idx) in state.data.sources" :key="idx">
              {{ source.article_version.chapter_no }}（{{ source.relation_type }}）
            </li>
          </ul>
        </div>
        <p v-else class="no-source">暂无已确认来源</p>
      </template>
    </div>
  </span>
</template>

<style scoped>
.concept-hyperlink-wrapper {
  position: relative;
  display: inline-block;
}
.concept-hyperlink {
  background: none;
  border: none;
  padding: 0;
  color: #1a5fb4;
  text-decoration: underline dotted;
  cursor: pointer;
  font: inherit;
}
.concept-popover {
  position: absolute;
  z-index: 10;
  top: 100%;
  left: 0;
  width: 280px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 13px;
}
.review-badge {
  font-size: 11px;
  color: #b45309;
  background: #fef3c7;
  padding: 2px 6px;
  border-radius: 3px;
}
.sources ul {
  margin: 4px 0 0;
  padding-left: 16px;
}
.no-source {
  color: #999;
}
</style>
