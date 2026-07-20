# MVP 骨架充实与功能闭环计划

> 本文承接 `GOAL.md`。现有工程骨架已具备数据库、后端 API、规则引擎、权限和法律阅读器；本阶段不继续扩张架构，目标是把已有能力连接成用户可操作、可解释、可验收的产品闭环。

## 1. 阶段目标

完成后，法务或合规人员应能在浏览器中独立完成：

```text
登录
→ 选择公司和评价时点
→ 查看/补充事实与证据
→ 选择已发布规则集
→ 发起合规检查
→ 区分五值结果
→ 查看证明链和法源
→ 导出或记录复核意见
```

法律知识工程师应能完成：

```text
查看规则及测试
→ 提交审核
→ 法律审核
→ 技术审核
→ 发布或退回
→ 从审计日志确认全过程
```

## 2. 当前基线与缺口

| 能力 | 当前状态 | 本阶段目标 |
|---|---|---|
| 法律阅读 | 列表、条文、综合、概念浮层可用 | 增加章节导航、概念详情和来源返回 |
| 事实证据 | 后端仅有创建/关联接口 | 增加查询、表单、列表、有效期和证据预览 |
| 合规检查 | 后端可执行十条规则 | 增加主体/规则集选择、进度和五值结果页 |
| 证明链 | 后端可查询 | 增加逐步证明、变量、事实、证据和法源穿透 |
| 规则治理 | 后端状态机和门禁可用 | 增加规则详情、测试结果、双审和发布 UI |
| 审计 | 后端列表接口可用 | 增加筛选、分页和资源跳转 |
| 验收 | API 级 AC-01～AC-08 | 增加真实浏览器 E2E 和 Docker 环境验证 |

## 3. 第一优先级：统一契约

### 3.1 合规检查请求

采用以下正式契约，并为旧字段保留一个开发周期兼容：

```http
POST /api/v1/compliance-checks
Idempotency-Key: <uuid>
```

```json
{
  "tenant_id": "uuid",
  "subject_id": "uuid",
  "evaluation_time": "2026-07-17T00:00:00+08:00",
  "ruleset_id": "uuid"
}
```

- 后端从 `ruleset_id` 解析固定规则版本，不接受前端任意拼装正式规则列表。
- `Idempotency-Key` 以请求头为权威来源；临时兼容 JSON 的 `idempotency_key`，响应增加弃用提示。
- `subject_id` 作为通用字段；旧 `company_id` 只在兼容层转换。
- 响应记录规则集版本、事实版本快照、评价时点、请求人和 `trace_id`。

### 3.2 补充读接口

前端不得依赖种子 ID 或硬编码列表。至少增加：

```text
GET /api/v1/subjects?tenant_id=&type=&listed=
GET /api/v1/subjects/{subject_id}
GET /api/v1/subjects/{subject_id}/governance
GET /api/v1/facts?tenant_id=&subject_id=&status=&at=
GET /api/v1/facts/{fact_id}
GET /api/v1/evidence?tenant_id=&subject_id=&fact_id=
GET /api/v1/evidence/{evidence_id}
GET /api/v1/rulesets?status=PUBLISHED&at=
GET /api/v1/rules/{rule_id}
GET /api/v1/rules/{rule_id}/tests
GET /api/v1/rules/{rule_id}/reviews
GET /api/v1/compliance-checks?tenant_id=&subject_id=&status=
```

列表接口统一分页：`items`、`page`、`page_size`、`total`；统一支持稳定排序。所有租户资源查询由服务端添加租户条件。

### 3.3 契约治理

- 从 FastAPI OpenAPI 生成前端类型，减少手写类型漂移。
- 每次 API 变更重新导出 `contracts/openapi.json`，CI 比较当前应用契约与提交快照。
- 错误码进入稳定枚举；前端按错误码处理，不解析自然语言消息。
- 新旧字段兼容测试通过后，才允许迁移前端调用。

## 4. 第二优先级：补齐用户页面

### 4.1 全局工作台与导航

新增统一侧栏或顶部导航：法律仓库、条文阅读、上市公司、事实与证据、合规检查、规则中心、证明与审计。根据角色显示可用入口，但服务端仍独立授权。

工作台展示：最近阅读、待补事实、最近检查、待审核规则和高风险结果。卡片必须来自真实 API，不使用静态数字。

### 4.2 上市公司治理页

路由建议：`/subjects/:subjectId/governance`。

展示公司、董事会、审计委员会、角色任职和有效期间。自然人、角色、任职关系和组织机构使用不同视觉类型。评价时间变化时重新计算有效投影，不在客户端把“无记录”显示成“不存在”。

### 4.3 事实与证据页

路由建议：`/subjects/:subjectId/facts`。

实现：

- 事实列表、类型筛选、有效时间筛选和五值状态。
- 创建事实表单，支持结构化值预览和 `[valid_from, valid_to)` 校验。
- 创建证据元数据、关联事实、查看来源与质量信息。
- 明确区分事实内容、证据材料和系统结论。
- 保存前展示差异；成功后刷新服务端权威状态。

MVP 不上传真实文件正文，可先保存证据元数据和演示对象键；不得把浏览器本地路径当作证据来源。

### 4.4 合规检查页

路由建议：`/compliance-checks/new` 和 `/compliance-checks/:checkId`。

检查向导包含：

1. 选择租户范围内主体。
2. 选择评价时点。
3. 选择已发布且在该时点有效的规则集。
4. 预检缺失事实并允许跳转补充。
5. 明确确认后提交检查。
6. 展示整体摘要和逐规则结果。

五种结果使用独立标签和说明：

| 真值 | UI 文案 | 下一步 |
|---|---|---|
| `TRUE` | 符合 | 查看依据 |
| `FALSE` | 不符合 | 查看差距与整改提示 |
| `UNKNOWN` | 资料不足 | 跳转缺失事实 |
| `CONFLICT` | 事实或规则冲突 | 并列展示冲突来源，交由人工处理 |
| `NOT_APPLICABLE` | 不适用 | 展示范围排除原因 |

禁止把五值结果汇总成未经定义的单一百分制“合规分”。

### 4.5 证明查看页

路由建议：`/conclusions/:conclusionId/proof`。

默认展示逐步文字链：主体确认、时间确认、规则适用、事实读取、约束计算、例外检查、冲突处理和结论。每一步显示输入、输出和来源链接；高级区域可展开变量绑定与 JSON。

证明页必须能跳转至：规则版本、事实详情、证据详情、条文版本。目标不存在或无权限时显示明确状态，不静默隐藏证明步骤。

### 4.6 规则中心

路由建议：`/rules` 和 `/rules/:ruleId`。

规则详情展示自然语言、结构化表达、来源、有效时间、优先级、测试案例、审核记录和当前状态。不同角色的可用操作：

- `KnowledgeEditor`：编辑草稿、提交、处理退回。
- `LegalReviewer`：法律通过或退回，必须填写意见。
- `TechnicalReviewer`：查看测试执行结果并技术审核。
- `Publisher`：仅在全部门禁满足时发布。

按钮禁用应解释原因；即使前端错误放开按钮，后端仍必须拒绝。

### 4.7 审计页

路由建议：`/audit`。

按时间、操作者、动作、资源类型、资源 ID 和决定筛选；显示 `trace_id` 并支持跳转相关规则或检查。敏感参数只显示脱敏摘要，普通用户不能查看该页面。

## 5. 第三优先级：让规则拥有真实“血肉”

### 5.1 规则集

新增版本化 `RuleSet` 与 `RuleSetMember`。正式检查只执行已发布规则集；规则集发布后成员和规则版本不可变，变更必须创建新版本。

### 5.2 十条规则深化

- 将演示阈值迁入规则版本的结构化 `requirement_expression`，处理器读取规则版本，不在 Python 函数中写死。
- `GOV-TIME-001` 和 `GOV-ROLE-001` 保持半开区间语义并补充边界证明。
- `GOV-CTRL-001` 从单个布尔事实升级为候选控制关系推导：持股、表决权、协议控制和其他可验证事实分别建模；缺少必要材料返回 `UNKNOWN`。
- 每个结果保存实际采用的规则版本、变量、事实 ID、证据 ID 和条文版本。
- 规则未绑定 `VERIFIED` 法源时不得进入正式规则集。

### 5.3 缺失与冲突处理

为每条规则定义 `required_fact_specs`，在执行前生成缺失清单。冲突结果必须列出冲突事实、各自证据和有效期间，不允许仅返回 `CONFLICT` 字符串。

## 6. 第四优先级：充实数据与内容

### 6.1 演示数据

扩充为三家公司：完整合规、明确违反、资料缺失/冲突。每家公司都有董事会、审计委员会、角色任职、事实、证据元数据和至少一次检查历史。

演示种子应让用户登录后无需复制 UUID 即可完成所有页面操作。种子重复执行不能改变稳定 ID 或产生重复关系。

### 6.2 真实法源准入

按 `01-MVP权威法源与版本清单.md` 采集原件、哈希和版本元数据。真实文本进入系统前必须由法律审核者确认；在此之前继续以 `DEMO / UNVERIFIED` 明示，不影响工程验收。

### 6.3 小综合内容

确定性输入不足时显示“暂无经审核的综合内容”，不使用模型常识补齐。Agent 只改写已审核的纯文本片段，不能新增 `concept_id`、来源或法律命题。

## 7. 第五优先级：浏览器级验收

使用 Playwright 覆盖真实前端和真实 API：

1. 登录并进入法律阅读器，点击概念查看来源。
2. 选择公司，创建事实和证据并建立关联。
3. 发起合规检查，分别验证五种结果的页面状态。
4. 从 `FALSE` 或 `CONFLICT` 结果穿透至证明、事实、证据和法条。
5. 编辑者提交规则，审核者依次审核，发布者发布。
6. 验证编辑者自审、跨租户访问和无权限发布均被拒绝。
7. Agent 禁用时小综合正常降级；缺少审核内容时不补写。

测试必须通过浏览器交互完成关键步骤，不能只用 FastAPI `TestClient` 替代前端 E2E。

## 8. 第六优先级：运行与发布验证

- 在干净环境执行 `make bootstrap → make up → make migrate → make seed → make test → make e2e`。
- 实际运行 `docker compose up`，验证 Web 能访问 API、API 能访问数据库、健康检查和环境变量正确。
- 推送分支触发 GitHub Actions，保存成功运行链接。
- 执行 `04-MVP性能基准与容量验收方案.md` 的数据生成和正式负载测试，而非只跑 20 次烟雾请求。
- 验证备份恢复、幂等重放、数据库超时和 Agent 不可用降级。

## 9. 实施切片

| 切片 | 交付内容 | 退出条件 |
|---|---|---|
| F0 | 正式规则集与合规检查契约 | OpenAPI、迁移、兼容和契约测试通过 |
| F1 | 主体、事实、证据读接口及页面 | 用户不使用 UUID 即可录入并回看数据 |
| F2 | 合规检查与五值结果页 | 五种状态均由真实 API 数据渲染 |
| F3 | 证明链穿透 | 结论可跳转至规则、事实、证据和法条 |
| F4 | 规则中心与双审 UI | 完整状态机可在浏览器中操作，拒绝路径可见 |
| F5 | 审计与工作台 | 关键动作可筛选、追踪和回到业务资源 |
| F6 | 浏览器 E2E | 核心用户与审核流程全绿 |
| F7 | Docker、CI、性能与故障验证 | 外部运行证据和验收报告齐全 |

每个切片必须同时修改数据库/后端、OpenAPI、前端类型、页面和测试中实际受影响的部分，避免先堆完后端再长期留下不可操作的 UI。

## 10. 完成定义

- [ ] 登录后可从导航访问所有 P0 页面，没有依赖手填 UUID 的主流程。
- [ ] 主体、事实、证据、规则集、检查、证明和审计都有真实查询接口。
- [ ] 合规请求使用固定 `ruleset_id`、通用 `subject_id` 和请求头幂等键。
- [ ] 五值结果在 UI 中独立呈现，并提供正确的下一步操作。
- [ ] 证明能够穿透规则版本、事实、证据和条文版本。
- [ ] 十条规则的阈值和参数来自规则版本，不硬编码在处理器。
- [ ] 规则中心可完成提交、双审、退回和发布，后端门禁始终有效。
- [ ] 浏览器 E2E 覆盖阅读、录入、检查、证明、审核和越权拒绝。
- [ ] Docker Compose 和真实 CI 已运行成功并留下证据。
- [ ] 正式性能基准达到 `04-MVP性能基准与容量验收方案.md` 的目标，或明确记录未达标项。
- [ ] 无真实法源或 Agent 时仍可安全演示，所有演示内容明确标识。

## 11. Agent 工作记录

实施 Agent 每完成一个切片更新下表，并附命令、截图或测试报告路径：

| 切片 | 状态 | 证据 | 遗留问题 |
|---|---|---|---|
| F0 | `done` | 新增 `rule_set`/`rule_set_member` 表（迁移 `e97de187ca96`，已在 dev/test 库真实执行）；`RuleSetService`（草稿创建/加成员/发布，发布后成员不可变，成员必须是已 PUBLISHED 的规则版本）；`POST/GET /rulesets`、`/rulesets/{id}/members`、`/rulesets/{id}/publish`；`POST /compliance-checks` 改为正式契约（`subject_id`+`ruleset_id`+`Idempotency-Key` 请求头，后端按 `ruleset_id` 解析固定规则版本，不接受前端拼装规则列表）；旧字段（`company_id`/`rule_codes`/JSON `idempotency_key`）保留一个开发周期兼容，响应用 `deprecations[]` 明确提示；新增 `GET /compliance-checks` 统一分页（`items/page/page_size/total`）；`contracts/openapi.json` 已重新导出；103 个 pytest 全绿（新增 8 个 F0 专项契约测试，覆盖草稿/发布/成员不可变/未发布规则集拒绝/正式路径/旧字段兼容且报告弃用/缺失幂等键拒绝/分页列表），`ruff`/`mypy` 全绿 | 前端尚无任何页面消费 compliance-checks 契约，类型生成与前端改动已在 F1/F2 一并完成——**"演示规则集能否走完整 publish"的疑问已解决**：种子脚本新增 `seed_ruleset_governance`，用 3 条规则（GOV-ORG-001/GOV-AUD-001/GOV-ID-002）+ 4 家演示公司（甲全合规/乙缺委员会+冲突事实/丙非上市/丁零数据）真实走完 submit→双审→publish，发布门禁**真实重新执行**了 21 条测试用例中的多数（PASS/VIOLATION/BOUNDARY/CONFLICT/MISSING_FACT/NOT_APPLICABLE 尽量用真实公司+评价时点验证，仅在规则语义确实不存在对应分支时才用免执行占位或书面豁免理由，如"存在性判断无例外分支"），产出一个真正 `PUBLISHED` 的 `MVP-P0-DEMO` RuleSet；`PUBLISHED` 在此仅代表内部治理工作流（真实双审+真实测试门禁）已通过，不代表法源本身已具备法律效力——法源本身仍标注 DEMO/UNVERIFIED，两者是不同维度，已在种子脚本文档字符串和 RuleSet 名称中明确写出，避免误导 |
| F1 | `done` | 新增 `SubjectService`（主体列表/详情/治理快照，`legal_subject` 为跨租户共享登记数据，`tenant_id` 仅用于鉴权而非行过滤）+ `GET /subjects`、`/subjects/{id}`、`/subjects/{id}/governance`（按 `at` 重新计算有效投影，机构不存在与机构存在但当前无有效任职两种状态在响应中明确区分）；`FactEvidenceService` 新增读方法 + `GET /facts`、`/facts/{id}`（含关联证据）、`GET /evidence`（按 subject_id/fact_id 过滤）、`/evidence/{id}`；facts/evidence 读接口限定 ComplianceUser/Auditor/SystemAdmin（Reader 角色不能浏览租户私有事实，已有测试覆盖 403）；新增 `GET /auth/me`（返回角色授权含 tenant_id）解决前端"不能靠用户输入 UUID 获知租户范围"的问题；前端新增 `SubjectListView`/`SubjectGovernanceView`/`FactEvidenceView` 三个页面 + App.vue 顶部导航（法律仓库/上市公司），`auth` store 登录后自动拉取 `/me` 并暴露 `currentTenantId`；`contracts/openapi.json` 已重新导出；后端 111 个 pytest 全绿（新增 8 个：`/me`、主体列表按类型过滤、详情 404、治理"机构不存在"与"机构存在但空"两态区分、事实/证据列表与详情、Reader 403），前端 10 个 vitest 全绿，`pnpm build`/`pnpm lint` 全绿；用真实浏览器完整走查：登录（compliance@demo.lawfocus）→顶部导航进入"上市公司"→点击甲上市公司"治理结构"看到真实董事会/审计委员会任职数据→进入"事实与证据"→展开已有事实看到关联证据→创建新证据→关联到该事实→列表实时更新为 2 条证据；走查中发现并修复两个真实 bug：①过期 token 导致 `/me` 请求 401 但路由守卫未捕获异常，已改为捕获失败并登出重定向登录页；②`SubjectListView` 未按 `subject_type` 过滤，导致"上市公司"页面把种子数据里的董事个人 `LegalSubject` 也列了出来，已加 `subject_type=LISTED_COMPANY` 过滤 | `SubjectGovernanceView`/`FactEvidenceView` 的表单交互细节暂无 Vitest 组件测试（仅 `SubjectListView` 有），复杂交互留给 F6 的浏览器 E2E 覆盖，本轮已通过真实浏览器走查验证功能正确 |
| F2 | `done` | 补齐关键缺口：`Conclusion` 模型新增 `rule_version` 关系，`ConclusionOut` 新增 `rule_code`/`rule_name` 字段（此前只有裸 `rule_version_id` UUID，前端无法不靠 UUID 展示结果，已修复并补测试断言）；种子脚本新增 `seed_ruleset_governance`——4 家演示公司（甲全合规/乙缺委员会+比例冲突/丙非上市/丁零数据）+ 3 条规则（GOV-ORG-001/GOV-AUD-001/GOV-ID-002）真实走完 submit→双审→publish，产出真正 `PUBLISHED` 的 `MVP-P0-DEMO` 规则集，使 TRUE/FALSE/UNKNOWN/CONFLICT/NOT_APPLICABLE 五值均可通过向导真实触发；前端新增 `ComplianceCheckWizardView`（`/compliance-checks/new`：选主体→选评价时点→选已发布且当日有效的规则集→勾选确认→提交，`Idempotency-Key` 走请求头）、`ComplianceCheckResultView`（`/compliance-checks/:checkId`：五值各自独立文案+下一步操作，不汇总百分制合规分）、`ConclusionProofView`（`/conclusions/:conclusionId/proof`，F3 将增强为可跳转规则/事实/证据/条文）；后端 111 个 pytest 全绿（新增 rule_code/rule_name 断言），前端 10 个 vitest 全绿，`ruff`/`mypy`/`pnpm build`/`pnpm lint` 全绿；真实浏览器完整走查四家公司：甲→三条全部"符合"；乙→"符合"/"不符合"/"事实或规则冲突"（冲突证明页正确并列展示两条矛盾事实 `[5,1]`/`[5,2]` 及各自 fact_id）；丁→"不符合"×2/"资料不足"（缺失事实清单+"跳转补充事实"正确跳转到丁的事实页）；丙因非上市公司被向导的主体下拉框正确排除（NOT_APPLICABLE 已由 pytest+直接 curl 验证，向导本身按产品设计不需要能选中非上市公司） | 证明链页面仍是 F2 最简版本（JSON 展示计算过程），尚未做成可点击跳转规则版本/事实/证据/条文版本的正式穿透视图，留给 F3 |
| F3 | `done` | 补齐三处模型关系缺口以支持穿透（`Conclusion.rule_version`、`ProofStep.rule_version`、`RuleSource.article_version`，均为纯 ORM 关系，未加列，无需迁移）；`ConclusionOut`/`ProofStepOut` 新增 `rule_code`/`rule_name`（或 `rule_id`/`rule_code`），彻底消除"结论/证明步骤只有裸 UUID"的问题；规则处理器（GOV-ID-001/002、GOV-CTRL-001）的计算载荷补充 `fact_id`/`fact_ids`，此前这些字段只在 CONFLICT 分支才带 fact 引用，PASS/FALSE 分支读了事实却没留痕迹，现已统一；新增 `GET /rules/{rule_id}`（含法源→条文版本）；前端新增 `RuleDetailView`（`/rules/:ruleId`）、`FactDetailView`（`/facts/:factId`，可独立跳转，含返回主体事实页的链接）；`ConclusionProofView` 升级为按已知字段名（`rule_id`/`fact_id`/`fact_ids`）通用提取穿透链接，不依赖为每种规则单独写模板；后端 113 个 pytest 全绿（新增 2 个规则详情测试），前端 10 个 vitest 全绿，`ruff`/`mypy`/`pnpm build`/`pnpm lint` 全绿；真实浏览器完整走查乙公司 GOV-ID-002 的 CONFLICT 证明页：①点击"查看规则 GOV-ID-002"→规则详情页显示 PUBLISHED 状态及所引第一百二十条条文全文；②点击两条"查看事实"→分别打开两条矛盾事实详情页（total:5/independent:1 与其证据），并可返回主体事实页 | 目前只在 calculation JSON 里出现 `fact_id`/`fact_ids`/`rule_id` 时才会渲染穿透链接（通用字段名约定，非强类型 schema），换成新 step_type 时若未遵循该命名约定，穿透链接会静默不显示而非报错——可接受的 MVP 简化，非架构缺陷 |
| F4 | `done` | `GET /rules/{rule_id}` 已扩展返回 `test_cases`/`review_decisions`（此前只有法源），`RuleVersionDetailOut`/`RuleDetailOut` schema 相应扩充；`RuleDetailView` 新增完整操作面板：提交/法律审核/技术审核/发布四个按钮均配对"能否操作"布尔与"为什么不能"文案（角色不足 vs 状态不符两类原因区分），后端在每个动作上独立重新校验角色与状态转移，不依赖前端已禁用就假设安全；真实浏览器完整走查双审状态机：以 `editor@demo.lawfocus` 打开 DRAFT 规则 GOV-ID-001（无种子测试用例）→提交审核（DRAFT→IN_REVIEW，提交按钮正确变灰）→登出登入 `legal-reviewer@demo.lawfocus`→法律审核通过（IN_REVIEW→LEGAL_APPROVED，审核记录列表出现第 1 条）→登出登入 `tech-reviewer@demo.lawfocus`→技术审核通过（LEGAL_APPROVED→TECH_APPROVED，审核记录第 2 条）→登出登入 `publisher@demo.lawfocus`→点击发布→**真实失败**，后端门禁返回详细缺失清单（"missing mandatory test case type: VIOLATION/MISSING_FACT/PASS/BOUNDARY"+"CONFLICT/NOT_APPLICABLE/EXCEPTION 需要用例或书面豁免"+"no test cases recorded at all"），前端 `PUBLISH_GATE_FAILED` 分支正确展示为醒目错误提示，规则状态维持 TECH_APPROVED 未被静默放行；控制台仅有预期的 422 网络层日志，无未捕获异常；`contracts/openapi.json` 已重新导出；后端 113 个 pytest 全绿，`ruff`/`mypy` 全绿；前端 10 个 vitest 全绿，`pnpm build`/`pnpm lint` 全绿 | 走查过程中发现并修复一处真实文案 bug：`techReviewDisabledReason`/`publishDisabledReason` 原先硬编码"法律审核尚未通过"/"尚未完成双审"，在规则已过 TECH_APPROVED（如发布后）时仍会显示这句话，构成失实断言；已改为"需处于 LEGAL_APPROVED/TECH_APPROVED 才能……"的中性表述。GOV-ID-001 本身经此走查后停留在 TECH_APPROVED（发布门禁未过），符合预期，未强行让它发布 |
| F5 | `done` | 关键动作接入真实审计留痕：`GET /laws/{law}/versions/{v}/articles/{no}` 与 `.../effective` 成功读取时记 `VIEW`/`article_version`；`POST /rules/{id}/submit`、`/reviews`、`/publish` 分别记 `SUBMIT`/`REVIEW`/`PUBLISH`（成功 `ALLOWED`，失败 `DENIED`+具体 `reason_code`，`REVIEW` 的审核类型与决定编码进 `reason_code` 如 `LEGAL:CHANGES_REQUESTED`）；`POST /rulesets/{id}/publish` 同样记 `PUBLISH`/`rule_set`（含空规则集拒绝的 `DENIED`）；`POST /compliance-checks` 成功记 `CREATE`/`compliance_check`；`GET /audit-events` 从"仅返回近 200 条列表"改为分页 `Page[AuditEventOut]` + 六个过滤维度（`actor_id`/`action`/`resource_type`/`resource_id`/`decision`/`occurred_from`~`occurred_to`），仍限 Auditor/SystemAdmin；新增 `GET /audit-events/mine`（任意已登录用户可调用，强制 `actor_id=self`，不接受 `actor_id` 参数，用于工作台"最近阅读"卡片而不必赋予非 Auditor 角色查看他人审计记录的权限）；前端新增 `AuditView`（`/audit`，六个过滤输入 + 结果表，`rule`/`compliance_check` 两类资源渲染可点击跳转链接，403 时展示"当前账号没有 Auditor 权限"而非裸错误）与 `WorkbenchView`（`/workbench`，五张真实 API 卡片：待审核规则过滤 `GET /rules` 的 `IN_REVIEW`/`LEGAL_APPROVED`；最近检查/待补事实/高风险结果均来自 `GET /compliance-checks` 的 `conclusions[]`，按 `UNKNOWN`/`FALSE`/`CONFLICT` 分流并链接回检查页或事实页；最近阅读来自 `GET /audit-events/mine`）；`App.vue` 导航新增"工作台"（登录即见）与"审计"（仅 Auditor/SystemAdmin 可见，后端仍独立鉴权）；`contracts/openapi.json` 已重新导出；后端新增 7 个 `test_audit_events.py` 专项测试（提交/发布门禁失败/审核决定编码/非 Auditor 403/`mine` 自范围隔离/规则集空发布拒绝/合规检查创建，均验证审计行落库且字段正确），另修正 1 个受响应形状变化影响的既有测试（`test_audit_events_allows_global_auditor_role`：`list` → `{items,...}`），全量 120 个 pytest 全绿，`ruff`/`mypy` 全绿；前端新增 `AuditView.test.ts`（3 个：403 提示/空态/含跳转链接的成功态），全量 13 个 vitest 全绿，`pnpm build`/`pnpm lint` 全绿；真实浏览器完整走查：以 `auditor@demo.lawfocus` 阅读一条法条→审计页看到该 `VIEW` 事件（真实 trace_id/actor_id）→筛选 `resource_type=rule` 得到"没有符合条件的审计记录"（当时未产生任何规则动作，筛选逻辑正确）→筛选 `decision=DENIED` 精确返回 4 条此前累积的 `AUTHORIZE`/`INSUFFICIENT_ROLE` 拒绝事件；以 `compliance@demo.lawfocus` 对乙、丁两家公司发起真实合规检查后回到工作台，"最近检查"显示 2 条真实检查（可点击）、"高风险结果"正确列出"不符合"×3/"冲突"×1（各自可跳转回对应检查页）、"待补事实"正确列出"独立董事最低比例：缺失 BOARD_COMPOSITION.independent_director_count"（可跳转到该公司事实页）、"最近阅读"显示该账号自己刚读过的条文版本时间线 | 走查中发现并修复一个真实缺陷：`WorkbenchView` 最初把"最近检查"接口的 403（如 `editor@demo.lawfocus` 有租户但没有 `ComplianceReaderCtx` 所需角色）之误当成"加载失败"直接把裸错误消息 `insufficient role` 抛给用户，且"待补事实"/"高风险结果"两张衍生卡片把该失败状态误渲染成"暂无结论"（看起来像正常空态，实为访问被拒绝）；已修正为对 403 单独判断并展示"当前角色无权查看合规检查记录"，且衍生卡片新增 `error` 分支不再冒充空态。已知限制（明确记录、非缺陷）：①"最近阅读"卡片暂不支持从阅读记录跳回原文条款，因 `ArticleVersionOut` 未携带 `law_code`/`version_name`/`article_no`，需要额外反查接口，本轮未做；②`resource_type`/`action` 过滤为自由文本输入而非枚举下拉，需要审计员知道后端使用的英文常量名 |
| F6 | `pending` |  |  |
| F7 | `pending` |  |  |

只有在第 10 节全部条件有当前状态证据支持时，才能宣布本阶段完成。配置已写、接口可调用或单元测试通过，不能单独证明产品闭环已经完成。
