export interface LegalVersion {
  id: string
  version_name: string
  promulgated_at: string | null
  effective_from: string
  effective_to: string | null
  status: string
}

export interface Law {
  id: string
  code: string
  name: string
  document_type: string
  issuer: string | null
  jurisdiction: string | null
  versions: LegalVersion[]
}

export interface ArticleVersion {
  id: string
  article_id: string
  article_no: string
  legal_version_id: string
  chapter_no: string | null
  section_no: string | null
  article_text: string
  valid_from: string
  valid_to: string | null
  created_at: string
}

export interface ArticleSummary {
  article_no: string
  chapter_no: string | null
  section_no: string | null
  summary: string
}

export interface ArticleNavigation {
  current: ArticleVersion
  previous_article_no: string | null
  next_article_no: string | null
}

export interface ConceptSource {
  article_version: ArticleVersion
  relation_type: string
}

export interface ConceptDetail {
  id: string
  code: string
  name: string
  concept_type: string
  status: string
  definition: string
  review_status: string
  valid_from: string
  valid_to: string | null
  sources: ConceptSource[]
}

export interface ConceptPreview {
  id: string
  code: string
  name: string
  concept_type: string
  review_status: string
  short_definition: string
}

export interface TextSegment {
  text: string
  concept_id: string | null
}

export interface Synthesis {
  article_version_id: string
  text_segments: TextSegment[]
  generated_by: string
}

export interface RuleSynthesis {
  article_version_id: string
  rule_id: string
  rule_code: string
  rule_name: string
  text_segments: TextSegment[]
  generated_by: string
}

export interface ApiErrorBody {
  code: string
  message: string
  trace_id: string
  details?: Record<string, unknown> | null
}

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface RoleGrant {
  role_code: string
  tenant_id: string | null
}

export interface Me {
  user_id: string
  email: string
  display_name: string
  grants: RoleGrant[]
}

export interface Subject {
  id: string
  subject_type: string
  name: string
  unified_credit_code: string | null
  listed: boolean
  exchange: string | null
}

export interface Organization {
  id: string
  organization_type: string
  name: string
}

export interface RoleAssignmentEntry {
  id: string
  person_id: string
  person_name: string
  role_type_code: string
  role_type_name: string
  valid_from: string
  valid_to: string | null
  active_at_query_time: boolean
}

export interface OrganizationGovernance {
  organization: Organization
  members: RoleAssignmentEntry[]
}

export interface SubjectGovernance {
  subject: Subject
  at: string
  organizations: OrganizationGovernance[]
}

export interface Fact {
  id: string
  tenant_id: string
  company_id: string
  fact_type: string
  predicate: string
  object_value: Record<string, unknown>
  valid_from: string
  valid_to: string | null
  created_at: string
}

export interface Evidence {
  id: string
  tenant_id: string
  evidence_type: string
  title: string
  source_url: string | null
  source_file: string | null
  page_no: number | null
  quote_text: string | null
  published_at: string | null
  created_at: string
}

export interface EvidenceLinkSummary {
  evidence: Evidence
  support_type: string
  confidence: number | null
}

export interface FactDetail extends Fact {
  evidence: EvidenceLinkSummary[]
}

export interface RuleSetSummary {
  id: string
  code: string
  version_no: number
  name: string
  status: string
  effective_from: string | null
  effective_to: string | null
}

export interface RuleVersionSummary {
  id: string
  rule_code: string
  version_no: number
  status: string
}

export interface RuleSetDetail extends RuleSetSummary {
  members: RuleVersionSummary[]
}

export type TruthValue = 'TRUE' | 'FALSE' | 'UNKNOWN' | 'CONFLICT' | 'NOT_APPLICABLE'

export interface Conclusion {
  id: string
  rule_version_id: string
  rule_code: string
  rule_name: string
  result_status: TruthValue
  missing_facts: string[]
  applicable_reason: string | null
  excluded_reason: string | null
}

export interface PrecheckItem {
  rule_code: string
  rule_name: string
  status: TruthValue
  missing_facts: string[]
  applicable_reason: string | null
  excluded_reason: string | null
}

export interface PrecheckResult {
  items: PrecheckItem[]
}

export interface ComplianceCheck {
  id: string
  tenant_id: string
  subject_id: string
  evaluation_time: string
  rule_set_id: string | null
  ruleset_snapshot: Array<{ rule_code: string; rule_version_id: string }>
  status: string
  conclusions: Conclusion[]
  deprecations: string[]
}

export interface ProofStep {
  sequence_no: number
  step_type: string
  rule_version_id: string | null
  rule_id: string | null
  rule_code: string | null
  input_facts: Record<string, unknown>
  calculation: Record<string, unknown>
  output_state: Record<string, unknown>
}

export interface Proof {
  id: string
  conclusion_id: string
  root_step_id: string | null
  steps: ProofStep[]
}

export interface RuleSourceEntry {
  article_version: ArticleVersion
  relation_type: string
}

export interface RuleTestCaseEntry {
  id: string
  case_type: string
  expected_status: string
  input_facts: Record<string, unknown>
  not_applicable_reason: string | null
}

export interface ReviewDecisionEntry {
  id: string
  reviewer_user_id: string
  reviewer_display_name: string
  review_type: string
  decision: string
  comment: string | null
  created_at: string
}

export interface RuleVersionDetail {
  id: string
  version_no: number
  status: string
  modality: string
  subject_type: string | null
  effective_from: string | null
  effective_to: string | null
  condition_expression: Record<string, unknown>
  requirement_expression: Record<string, unknown>
  submitted_by: string | null
  sources: RuleSourceEntry[]
  test_cases: RuleTestCaseEntry[]
  review_decisions: ReviewDecisionEntry[]
}

export interface RuleDetail {
  id: string
  code: string
  name: string
  latest_version: RuleVersionDetail | null
}

export interface RuleOut {
  id: string
  code: string
  name: string
  latest_version: RuleVersionSummary | null
}

export interface AuditEvent {
  id: string
  trace_id: string
  actor_id: string | null
  tenant_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  resource_version: string | null
  decision: string
  reason_code: string | null
  occurred_at: string
}
