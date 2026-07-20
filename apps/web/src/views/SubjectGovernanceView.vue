<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiGet } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { SubjectGovernance } from '../types/api'

const props = defineProps<{
  subjectId: string
}>()

const at = ref(new Date().toISOString().slice(0, 10))
const state = ref<RemoteState<SubjectGovernance>>({ status: 'initial' })

async function load() {
  state.value = { status: 'loading' }
  try {
    const snapshot = await apiGet<SubjectGovernance>(`/subjects/${props.subjectId}/governance?at=${at.value}`)
    state.value = { status: 'success', data: snapshot }
  } catch (err) {
    state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

watch(() => [props.subjectId, at.value], load, { immediate: true })
</script>

<template>
  <div class="governance-view">
    <h1>治理结构</h1>
    <label class="at-picker">
      评价时点
      <input v-model="at" type="date" />
    </label>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'">
      加载失败：{{ state.message }}
      <button @click="load">重试</button>
    </p>

    <template v-else-if="state.status === 'success'">
      <h2>{{ state.data.subject.name }}</h2>

      <p v-if="state.data.organizations.length === 0" class="empty-hint">
        暂无治理机构记录（未记录 ≠ 不存在，可能尚未录入）。
      </p>

      <section v-for="entry in state.data.organizations" :key="entry.organization.id" class="organ-section">
        <h3>{{ entry.organization.name }}（{{ entry.organization.organization_type }}）</h3>
        <p v-if="entry.members.length === 0" class="empty-hint">该机构暂无任职记录。</p>
        <table v-else class="member-table">
          <thead>
            <tr>
              <th>姓名</th>
              <th>角色</th>
              <th>有效期间</th>
              <th>评价时点状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="member in entry.members" :key="member.id" :class="{ inactive: !member.active_at_query_time }">
              <td>{{ member.person_name }}</td>
              <td>{{ member.role_type_name }}</td>
              <td>
                {{ member.valid_from }} 起
                <template v-if="member.valid_to">至 {{ member.valid_to }}</template>
              </td>
              <td>
                <span v-if="member.active_at_query_time" class="badge active">有效</span>
                <span v-else class="badge inactive-badge">评价时点无效</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>

<style scoped>
.governance-view {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}
.at-picker {
  display: block;
  margin-bottom: 16px;
  font-size: 14px;
}
.at-picker input {
  margin-left: 8px;
  padding: 4px 8px;
}
.organ-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.empty-hint {
  color: #999;
  font-style: italic;
}
.member-table {
  width: 100%;
  border-collapse: collapse;
}
.member-table th,
.member-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #eee;
  font-size: 14px;
}
tr.inactive {
  color: #999;
}
.badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
}
.badge.active {
  background: #dcfce7;
  color: #15803d;
}
.badge.inactive-badge {
  background: #fee2e2;
  color: #b91c1c;
}
</style>
