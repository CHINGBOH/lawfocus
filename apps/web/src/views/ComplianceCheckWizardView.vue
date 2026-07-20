<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPost } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { ComplianceCheck, Page, PrecheckResult, RuleSetSummary, Subject } from '../types/api'
import type { RemoteState } from '../types/remote'

const auth = useAuthStore()
const router = useRouter()

const subjects = ref<Subject[]>([])
const subjectsError = ref<string | null>(null)
const selectedSubjectId = ref('')

const evaluationDate = ref(new Date().toISOString().slice(0, 10))

const rulesets = ref<RuleSetSummary[]>([])
const rulesetsError = ref<string | null>(null)
const selectedRulesetId = ref('')

const precheckState = ref<RemoteState<PrecheckResult>>({ status: 'initial' })

const confirmed = ref(false)
const submitting = ref(false)
const submitError = ref<string | null>(null)

const canSubmit = computed(
  () => !!selectedSubjectId.value && !!selectedRulesetId.value && confirmed.value && !submitting.value,
)

async function loadSubjects() {
  subjectsError.value = null
  try {
    const page = await apiGet<Page<Subject>>('/subjects?subject_type=LISTED_COMPANY&page_size=200')
    subjects.value = page.items
  } catch (err) {
    subjectsError.value = err instanceof Error ? err.message : '加载失败'
  }
}

async function loadRulesets() {
  rulesetsError.value = null
  selectedRulesetId.value = ''
  try {
    const items = await apiGet<RuleSetSummary[]>(
      `/rulesets?status_filter=PUBLISHED&at=${evaluationDate.value}`,
    )
    rulesets.value = items
  } catch (err) {
    rulesetsError.value = err instanceof Error ? err.message : '加载失败'
  }
}

async function loadPrecheck() {
  if (!auth.currentTenantId || !selectedSubjectId.value || !selectedRulesetId.value) {
    precheckState.value = { status: 'initial' }
    return
  }
  precheckState.value = { status: 'loading' }
  try {
    const result = await apiGet<PrecheckResult>(
      `/compliance-checks/precheck?tenant_id=${auth.currentTenantId}&subject_id=${selectedSubjectId.value}` +
        `&evaluation_time=${evaluationDate.value}T00:00:00Z&ruleset_id=${selectedRulesetId.value}`,
    )
    precheckState.value =
      result.items.length === 0 ? { status: 'empty' } : { status: 'success', data: result }
  } catch (err) {
    precheckState.value = { status: 'error', message: err instanceof Error ? err.message : '加载失败' }
  }
}

onMounted(() => {
  loadSubjects()
  loadRulesets()
})
watch(evaluationDate, loadRulesets)
watch([selectedSubjectId, selectedRulesetId, evaluationDate], loadPrecheck)

async function submit() {
  if (!auth.currentTenantId) {
    submitError.value = '当前账号没有租户范围授权，无法发起检查'
    return
  }
  submitting.value = true
  submitError.value = null
  try {
    const idempotencyKey = crypto.randomUUID()
    const check = await apiPost<ComplianceCheck>(
      '/compliance-checks',
      {
        tenant_id: auth.currentTenantId,
        subject_id: selectedSubjectId.value,
        evaluation_time: `${evaluationDate.value}T00:00:00Z`,
        ruleset_id: selectedRulesetId.value,
      },
      { 'Idempotency-Key': idempotencyKey },
    )
    router.push({ name: 'compliance-check-result', params: { checkId: check.id } })
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : '提交失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="wizard">
    <h1>发起合规检查</h1>

    <section class="wizard-step">
      <h2>1. 选择主体</h2>
      <p v-if="subjectsError" class="error">加载失败：{{ subjectsError }}</p>
      <p v-else-if="subjects.length === 0">暂无可选主体。</p>
      <select v-else v-model="selectedSubjectId">
        <option value="" disabled>请选择上市公司</option>
        <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
    </section>

    <section class="wizard-step">
      <h2>2. 选择评价时点</h2>
      <input v-model="evaluationDate" type="date" />
    </section>

    <section class="wizard-step">
      <h2>3. 选择已发布且在该时点有效的规则集</h2>
      <p v-if="rulesetsError" class="error">加载失败：{{ rulesetsError }}</p>
      <p v-else-if="rulesets.length === 0" class="empty-hint">
        在该评价时点没有已发布且有效的规则集，请调整日期或联系规则中心发布规则集。
      </p>
      <select v-else v-model="selectedRulesetId">
        <option value="" disabled>请选择规则集</option>
        <option v-for="rs in rulesets" :key="rs.id" :value="rs.id">{{ rs.name }}（v{{ rs.version_no }}）</option>
      </select>
    </section>

    <section v-if="selectedSubjectId && selectedRulesetId" class="wizard-step">
      <h2>4. 预检结果</h2>
      <p v-if="precheckState.status === 'loading' || precheckState.status === 'initial'">预检中…</p>
      <p v-else-if="precheckState.status === 'error'" class="error">
        预检加载失败：{{ precheckState.message }}
        <button type="button" @click="loadPrecheck">重试</button>
      </p>
      <p v-else-if="precheckState.status === 'empty'" class="empty-hint">该规则集没有可预检的规则。</p>
      <ul v-else-if="precheckState.status === 'success'" class="precheck-list">
        <li v-for="item in precheckState.data.items" :key="item.rule_code" class="precheck-item">
          <span class="rule-name">{{ item.rule_name }}（{{ item.rule_code }}）</span>
          <span class="precheck-status" :class="`status-${item.status.toLowerCase()}`">
            {{
              { TRUE: '符合', FALSE: '不符合', UNKNOWN: '资料不足', CONFLICT: '事实或规则冲突',
                NOT_APPLICABLE: '不适用' }[item.status]
            }}
          </span>
          <template v-if="item.status === 'UNKNOWN' && item.missing_facts.length">
            <span class="missing-facts">缺失：{{ item.missing_facts.join('、') }}</span>
            <RouterLink :to="{ name: 'subject-facts', params: { subjectId: selectedSubjectId } }">
              去补充事实 →
            </RouterLink>
          </template>
        </li>
      </ul>
    </section>

    <section class="wizard-step">
      <h2>5. 确认后提交</h2>
      <p class="hint">
        提交前请确认：本次检查会读取主体在评价时点的当前事实与治理数据；若存在资料不足，结果会显示"资料不足"而非默认通过。
      </p>
      <label class="confirm-label">
        <input v-model="confirmed" type="checkbox" />
        我已确认以上信息，发起检查
      </label>
      <button :disabled="!canSubmit" type="button" @click="submit">
        {{ submitting ? '提交中…' : '发起合规检查' }}
      </button>
      <p v-if="submitError" class="error" role="alert">{{ submitError }}</p>
    </section>
  </div>
</template>

<style scoped>
.wizard {
  padding: 24px;
  max-width: 700px;
  margin: 0 auto;
}
.wizard-step {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
select,
input[type='date'] {
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  width: 100%;
  max-width: 400px;
}
.confirm-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
  font-size: 14px;
}
.precheck-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.precheck-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid #eee;
  font-size: 14px;
}
.precheck-status {
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.status-true {
  color: #1b7f3a;
  background: #e6f5eb;
}
.status-false {
  color: #b3261e;
  background: #fce8e6;
}
.status-unknown {
  color: #8a6d3b;
  background: #fdf3d9;
}
.status-conflict {
  color: #8a3b8a;
  background: #f6e6f6;
}
.status-not_applicable {
  color: #666;
  background: #f0f0f0;
}
.missing-facts {
  color: #888;
  font-size: 13px;
}
button {
  padding: 10px 20px;
  background: #1f2d3d;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.error {
  color: #c0392b;
  font-size: 13px;
}
.empty-hint {
  color: #999;
}
.hint {
  color: #888;
  font-size: 13px;
}
</style>
