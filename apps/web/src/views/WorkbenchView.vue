<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiGet, ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { RemoteState } from '../types/remote'
import type { AuditEvent, ComplianceCheck, Page, RuleOut } from '../types/api'

const auth = useAuthStore()

const rulesState = ref<RemoteState<RuleOut[]>>({ status: 'initial' })
const checksState = ref<RemoteState<ComplianceCheck[]>>({ status: 'initial' })
const readsState = ref<RemoteState<AuditEvent[]>>({ status: 'initial' })

async function loadRules() {
  rulesState.value = { status: 'loading' }
  try {
    const rules = await apiGet<RuleOut[]>('/rules')
    rulesState.value = rules.length === 0 ? { status: 'empty' } : { status: 'success', data: rules }
  } catch (err) {
    rulesState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

async function loadChecks() {
  const tenantId = auth.currentTenantId
  if (!tenantId) {
    checksState.value = { status: 'empty' }
    return
  }
  checksState.value = { status: 'loading' }
  try {
    const page = await apiGet<Page<ComplianceCheck>>(
      `/compliance-checks?tenant_id=${tenantId}&page_size=5`,
    )
    checksState.value = page.items.length === 0 ? { status: 'empty' } : { status: 'success', data: page.items }
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      checksState.value = { status: 'error', message: '当前角色无权查看合规检查记录' }
    } else {
      checksState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
    }
  }
}

async function loadReads() {
  readsState.value = { status: 'loading' }
  try {
    const page = await apiGet<Page<AuditEvent>>(
      '/audit-events/mine?action=VIEW&resource_type=article_version&page_size=5',
    )
    readsState.value = page.items.length === 0 ? { status: 'empty' } : { status: 'success', data: page.items }
  } catch (err) {
    readsState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(() => {
  loadRules()
  loadChecks()
  loadReads()
})

const pendingReviewRules = computed(() =>
  rulesState.value.status === 'success'
    ? rulesState.value.data.filter(
        (r) => r.latest_version && ['IN_REVIEW', 'LEGAL_APPROVED'].includes(r.latest_version.status),
      )
    : [],
)

const missingFactItems = computed(() => {
  if (checksState.value.status !== 'success') return []
  return checksState.value.data.flatMap((check) =>
    check.conclusions
      .filter((c) => c.result_status === 'UNKNOWN')
      .map((c) => ({
        checkId: check.id,
        subjectId: check.subject_id,
        ruleName: c.rule_name,
        missing: c.missing_facts,
      })),
  )
})

const highRiskItems = computed(() => {
  if (checksState.value.status !== 'success') return []
  return checksState.value.data.flatMap((check) =>
    check.conclusions
      .filter((c) => c.result_status === 'FALSE' || c.result_status === 'CONFLICT')
      .map((c) => ({ checkId: check.id, ruleName: c.rule_name, status: c.result_status })),
  )
})
</script>

<template>
  <div class="workbench">
    <h1>工作台</h1>

    <div class="cards">
      <section class="card">
        <h2>待审核规则</h2>
        <p v-if="rulesState.status === 'initial' || rulesState.status === 'loading'">加载中…</p>
        <p v-else-if="rulesState.status === 'error'" class="error">{{ rulesState.message }}</p>
        <p v-else-if="pendingReviewRules.length === 0" class="empty-hint">暂无待审核规则。</p>
        <ul v-else>
          <li v-for="rule in pendingReviewRules" :key="rule.id">
            <RouterLink :to="{ name: 'rule-detail', params: { ruleId: rule.id } }">
              {{ rule.name }}（{{ rule.code }}）
            </RouterLink>
            <span class="tag">{{ rule.latest_version?.status }}</span>
          </li>
        </ul>
      </section>

      <section class="card">
        <h2>最近检查</h2>
        <p v-if="!auth.currentTenantId" class="empty-hint">当前账号无租户范围，不适用。</p>
        <p v-else-if="checksState.status === 'initial' || checksState.status === 'loading'">加载中…</p>
        <p v-else-if="checksState.status === 'error'" class="error">{{ checksState.message }}</p>
        <p v-else-if="checksState.status === 'empty'" class="empty-hint">暂无合规检查记录。</p>
        <ul v-else-if="checksState.status === 'success'">
          <li v-for="check in checksState.data" :key="check.id">
            <RouterLink :to="{ name: 'compliance-check-result', params: { checkId: check.id } }">
              检查 {{ check.id.slice(0, 8) }}…
            </RouterLink>
            <span class="tag">{{ check.status }}</span>
          </li>
        </ul>
      </section>

      <section class="card">
        <h2>待补事实</h2>
        <p v-if="!auth.currentTenantId" class="empty-hint">当前账号无租户范围，不适用。</p>
        <p v-else-if="checksState.status === 'loading'">加载中…</p>
        <p v-else-if="checksState.status === 'error'" class="error">{{ checksState.message }}</p>
        <p v-else-if="missingFactItems.length === 0" class="empty-hint">暂无资料不足的结论。</p>
        <ul v-else>
          <li v-for="(item, idx) in missingFactItems" :key="idx">
            <RouterLink :to="{ name: 'subject-facts', params: { subjectId: item.subjectId } }">
              {{ item.ruleName }}：缺失 {{ item.missing.join('、') }}
            </RouterLink>
          </li>
        </ul>
      </section>

      <section class="card">
        <h2>高风险结果</h2>
        <p v-if="!auth.currentTenantId" class="empty-hint">当前账号无租户范围，不适用。</p>
        <p v-else-if="checksState.status === 'loading'">加载中…</p>
        <p v-else-if="checksState.status === 'error'" class="error">{{ checksState.message }}</p>
        <p v-else-if="highRiskItems.length === 0" class="empty-hint">暂无不符合或冲突结论。</p>
        <ul v-else>
          <li v-for="(item, idx) in highRiskItems" :key="idx">
            <RouterLink :to="{ name: 'compliance-check-result', params: { checkId: item.checkId } }">
              {{ item.ruleName }}
            </RouterLink>
            <span class="tag risk">{{ item.status === 'FALSE' ? '不符合' : '冲突' }}</span>
          </li>
        </ul>
      </section>

      <section class="card">
        <h2>最近阅读</h2>
        <p v-if="readsState.status === 'initial' || readsState.status === 'loading'">加载中…</p>
        <p v-else-if="readsState.status === 'error'" class="error">{{ readsState.message }}</p>
        <p v-else-if="readsState.status === 'empty'" class="empty-hint">暂无阅读记录。</p>
        <ul v-else-if="readsState.status === 'success'">
          <li v-for="event in readsState.data" :key="event.id">
            条文版本 {{ event.resource_id?.slice(0, 8) }}… · {{ event.occurred_at }}
          </li>
        </ul>
        <p v-if="readsState.status === 'success'" class="limitation-hint">
          暂不支持从阅读记录直接跳回原文（需要额外的条文反查接口），仅展示时间线。
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.workbench {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.card h2 {
  margin: 0 0 10px;
  font-size: 16px;
}
.card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.card li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  border-top: 1px solid #eee;
  padding-top: 8px;
}
.card li:first-child {
  border-top: none;
  padding-top: 0;
}
.tag {
  font-size: 11px;
  color: #666;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
}
.tag.risk {
  color: #c0392b;
  background: #fdecea;
}
.empty-hint {
  color: #999;
  font-size: 13px;
}
.error {
  color: #c0392b;
  font-size: 13px;
}
.limitation-hint {
  color: #aaa;
  font-size: 11px;
  margin-top: 8px;
}
</style>
