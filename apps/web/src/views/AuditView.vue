<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, ApiError } from '../api/client'
import type { RemoteState } from '../types/remote'
import type { AuditEvent, Page } from '../types/api'

const filters = reactive({
  action: '',
  resource_type: '',
  resource_id: '',
  decision: '',
  occurred_from: '',
  occurred_to: '',
})

const state = ref<RemoteState<Page<AuditEvent>>>({ status: 'initial' })

function buildQuery(): string {
  const params = new URLSearchParams()
  if (filters.action) params.set('action', filters.action)
  if (filters.resource_type) params.set('resource_type', filters.resource_type)
  if (filters.resource_id) params.set('resource_id', filters.resource_id)
  if (filters.decision) params.set('decision', filters.decision)
  if (filters.occurred_from) params.set('occurred_from', filters.occurred_from)
  if (filters.occurred_to) params.set('occurred_to', filters.occurred_to)
  params.set('page_size', '50')
  return params.toString()
}

async function load() {
  state.value = { status: 'loading' }
  try {
    const page = await apiGet<Page<AuditEvent>>(`/audit-events?${buildQuery()}`)
    state.value = page.items.length === 0 ? { status: 'empty' } : { status: 'success', data: page }
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      state.value = { status: 'error', message: '当前账号没有 Auditor 权限，无法查看审计日志' }
    } else {
      state.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
    }
  }
}

onMounted(load)

function linkFor(event: AuditEvent): { name: string; params: Record<string, string> } | null {
  if (!event.resource_id) return null
  if (event.resource_type === 'rule') {
    return { name: 'rule-detail', params: { ruleId: event.resource_id } }
  }
  if (event.resource_type === 'compliance_check') {
    return { name: 'compliance-check-result', params: { checkId: event.resource_id } }
  }
  return null
}
</script>

<template>
  <div class="audit">
    <h1>审计日志</h1>

    <form class="filters" @submit.prevent="load">
      <label>
        动作
        <input v-model="filters.action" placeholder="如 PUBLISH" />
      </label>
      <label>
        资源类型
        <input v-model="filters.resource_type" placeholder="如 rule" />
      </label>
      <label>
        资源 ID
        <input v-model="filters.resource_id" placeholder="资源 UUID" />
      </label>
      <label>
        决定
        <select v-model="filters.decision">
          <option value="">全部</option>
          <option value="ALLOWED">ALLOWED</option>
          <option value="DENIED">DENIED</option>
        </select>
      </label>
      <label>
        起始时间
        <input v-model="filters.occurred_from" type="datetime-local" />
      </label>
      <label>
        结束时间
        <input v-model="filters.occurred_to" type="datetime-local" />
      </label>
      <button type="submit">筛选</button>
    </form>

    <p v-if="state.status === 'initial' || state.status === 'loading'">加载中…</p>
    <p v-else-if="state.status === 'error'" class="error" role="alert">{{ state.message }}</p>
    <p v-else-if="state.status === 'empty'">没有符合条件的审计记录。</p>

    <table v-else-if="state.status === 'success'" class="audit-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>trace_id</th>
          <th>操作者</th>
          <th>动作</th>
          <th>资源</th>
          <th>决定</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="event in state.data.items" :key="event.id">
          <td>{{ event.occurred_at }}</td>
          <td class="trace">{{ event.trace_id }}</td>
          <td>{{ event.actor_id ?? '—' }}</td>
          <td>{{ event.action }}</td>
          <td>
            <RouterLink v-if="linkFor(event)" :to="linkFor(event)!">
              {{ event.resource_type }}:{{ event.resource_id }}
            </RouterLink>
            <span v-else>{{ event.resource_type }}{{ event.resource_id ? `:${event.resource_id}` : '' }}</span>
          </td>
          <td :class="event.decision === 'DENIED' ? 'denied' : 'allowed'">{{ event.decision }}</td>
          <td>{{ event.reason_code ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="state.status === 'success'" class="total-hint">共 {{ state.data.total }} 条，本页显示 {{ state.data.items.length }} 条</p>
  </div>
</template>

<style scoped>
.audit {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.filters label {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: #555;
  gap: 4px;
}
.filters input,
.filters select {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.filters button {
  padding: 8px 16px;
  background: #1f2d3d;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  height: 32px;
}
.audit-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  font-size: 13px;
}
.audit-table th,
.audit-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid #eee;
}
.trace {
  font-family: monospace;
  font-size: 11px;
  color: #888;
}
.denied {
  color: #c0392b;
  font-weight: 600;
}
.allowed {
  color: #2e7d32;
}
.total-hint {
  color: #888;
  font-size: 12px;
  margin-top: 8px;
}
.error {
  color: #c0392b;
}
</style>
