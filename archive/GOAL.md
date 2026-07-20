# Goal：完成经济法知识仓库 MVP 全栈骨架代码

> 本文件是编码 Agent 的执行目标。开始前必须阅读 `AGENTS.md` 和 `00-项目文档索引与实施顺序.md`，再按其中顺序阅读全部设计文档。本文规定交付边界；形式化语义冲突时，以 `法律形式化元模型与精确语义规约.md` 为最高依据。

## 1. 最终目标

在当前仓库内实现一个可以本地启动、迁移、测试和演示的全栈 MVP 骨架，跑通以下闭环：

```text
浏览法律与条文
→ 点击可溯源概念
→ 录入公司治理事实和证据元数据
→ 按固定评价时点与规则集执行确定性检查
→ 返回五值结论
→ 查看规则、事实、证据、法条和证明步骤
```

“骨架完成”不是只创建空目录、占位类或静态页面。核心对象、数据库迁移、API、规则执行、前端闭环、权限门禁和自动化测试必须可运行；尚待法律审核的数据使用明确的演示种子和 `UNVERIFIED` 状态，不得伪装成正式法律内容。

## 2. 技术栈

| 层 | 选择 |
|---|---|
| 前端 | Vue 3、Vite、TypeScript、Vue Router、Pinia、Vitest |
| 后端 | Python 3.12+、FastAPI、Pydantic、SQLAlchemy 2、Alembic |
| 数据库 | PostgreSQL，启用全文检索；图结构先用关系表 |
| 后台任务 | MVP 使用 FastAPI 后台任务或同步执行接口，保留任务抽象 |
| Agent | 独立适配器接口；默认 `DisabledAgentProvider`，无密钥也能运行 |
| 测试 | pytest、Vitest；端到端优先 Playwright |
| 工程 | `uv`、`pnpm`、Docker Compose、GitHub Actions |

使用当前稳定版本并提交锁文件。不要在第一阶段引入 Neo4j、Z3、Celery、Kubernetes 或微服务拆分；为以后替换保留清晰接口即可。

## 3. 目标目录

```text
lawfocus/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/v1/
│   │   │   ├── core/
│   │   │   ├── domain/
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   └── main.py
│   │   ├── migrations/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/
│       ├── src/
│       │   ├── api/
│       │   ├── components/
│       │   ├── router/
│       │   ├── stores/
│       │   ├── types/
│       │   └── views/
│       ├── tests/
│       └── package.json
├── contracts/openapi.json
├── data/demo/
├── docs/
├── scripts/
├── .env.example
├── docker-compose.yml
├── Makefile
└── README.md
```

可以合理调整目录，但必须保持前端、后端、契约、迁移、测试和演示数据边界清晰。不要移动或重写现有规范文档。

## 4. 不可违反的领域语义

1. 自然人、角色、任职关系和事件分离；禁止用 `Director(person)` 代替 `RoleAssignment`。
2. 法律文本、概念和可执行规则分离；每个已发布规则必须关联 `ArticleVersion`。
3. 事实、证据和结论分离；结论必须拥有证明链。
4. 真值固定为 `TRUE | FALSE | UNKNOWN | CONFLICT | NOT_APPLICABLE`，不得退化成布尔值。
5. 不存在记录不等于 `FALSE`；必要事实缺失返回 `UNKNOWN`。
6. 动态关系使用半开区间 `[valid_from, valid_to)`；交易时间与有效时间分离。
7. 规则冲突按 `(Authority, Specificity, ExceptionLevel, TemporalOrder)` 字典序处理；无法消解返回 `CONFLICT`。
8. 模型置信度与法律真值分开存储，任何 Agent 输出均不能直接成为已审核事实或规则。
9. 法律原文和已发布内容只增新版本，不原位覆盖。
10. 所有租户私有查询必须由后端强制加入 `tenant_id` 范围。

## 5. 后端交付

### 5.1 核心模型

至少实现以下表、枚举、约束、索引和 Alembic 迁移：

- 身份与治理：`tenant`、`user`、`role`、`user_role`。
- 法律仓库：`legal_document`、`legal_version`、`article`、`article_version`。
- 知识图谱：`concept`、`concept_version`、`graph_node`、`graph_edge`。
- 治理主体：`legal_subject`、`organization`、`role_type`、`role_assignment`、`event`。
- 推理输入：`fact`、`evidence`、`fact_evidence`。
- 规则治理：`legal_rule`、`legal_rule_version`、`rule_source`、`rule_test_case`、`review_decision`。
- 推理输出：`compliance_check`、`conclusion`、`proof`、`proof_step`。
- 系统治理：`audit_event`、`idempotency_record`。

数据库必须保护：稳定 ID、版本唯一性、有效区间合法性、枚举值、必要外键、追加式审计以及常用时间/租户/全文查询索引。

### 5.2 服务边界

实现并单元测试：

- `LegalRepositoryService`：法律版本、条文层级和有效版本选择。
- `ConceptService`：概念预览、详情、来源和审核状态。
- `FactEvidenceService`：事实与证据分开写入和关联。
- `RuleRegistry`：规则版本、来源、测试和发布门禁。
- `RuleEngine`：五值逻辑、时间适用、精确数量/比例比较、优先级和冲突。
- `ProofService`：生成可序列化的逐步证明，不依赖隐藏模型推理。
- `AuthorizationService`：RBAC、自审禁止和租户范围校验。
- `AuditService`：记录发布、拒绝、数据变更、导出和规则执行。
- `SynthesisService`：只组合已审核片段；Agent 不可用时提供确定性模板降级。

### 5.3 API v1

至少提供并写入 OpenAPI：

```text
GET  /health
GET  /api/v1/laws
GET  /api/v1/laws/{law_id}/versions/{version_id}/articles/{article_id}
GET  /api/v1/articles/{article_version_id}/synthesis
GET  /api/v1/concepts/{concept_id}/preview
GET  /api/v1/concepts/{concept_id}
POST /api/v1/facts
POST /api/v1/evidence
POST /api/v1/facts/{fact_id}/evidence/{evidence_id}
POST /api/v1/compliance-checks
GET  /api/v1/compliance-checks/{check_id}
GET  /api/v1/conclusions/{conclusion_id}/proof
GET  /api/v1/rules
POST /api/v1/rules/{rule_id}/submit
POST /api/v1/rules/{rule_id}/reviews
POST /api/v1/rules/{rule_id}/publish
GET  /api/v1/audit-events
```

所有写接口验证身份、权限、对象版本和业务不变量。`POST /compliance-checks` 接收 `subject_id`、`evaluation_time`、`ruleset_id` 和 `Idempotency-Key`，返回固定规则集版本、五值结论、缺失事实、适用/排除原因和 `proof_id`。

统一错误结构至少包含 `code`、`message`、`trace_id` 和可选 `details`；不要把堆栈、SQL、密钥或敏感证据返回客户端。

## 6. 规则引擎交付

为 `02-上市公司治理MVP十条规则清单.md` 中十个 Rule ID 建立可注册的处理器或通用 DSL 执行入口。允许先用经标识的演示来源和演示阈值跑通结构，但必须满足：

- 演示规则状态为 `DRAFT` 或 `UNVERIFIED`，不能通过正式发布门禁。
- 数量和比例采用确定性计算；比例用整数交叉相乘。
- `GOV-TIME-001`、`GOV-ROLE-001` 至少具备真实可执行逻辑。
- 其余规则即使采用通用比较器，也必须返回变量绑定和证明步骤。
- 每条规则包含通过、违反、边界、缺失、不适用测试；例外与冲突至少在规则集层有覆盖。
- 执行结果固定记录 `ruleset_id`、规则版本、评价时点和输入事实版本。

## 7. 前端交付

实现可操作而非纯静态的页面：

1. **法律仓库**：法律列表、版本选择和章节树。
2. **条文阅读器**：桌面三栏布局；中心条文，左侧目录，右侧分段小综合。
3. **概念交互**：`ConceptHyperlink`、轻量浮层、概念详情和原文跳转。
4. **事实与证据**：创建事实、创建证据元数据、建立关联并显示有效期间。
5. **合规检查**：选择主体、评价时点和规则集，执行检查并展示五种独立状态。
6. **证明查看**：逐步展示规则、变量、事实、证据和法源链接。
7. **规则中心骨架**：列表、状态、测试结果、提交审核和发布按钮；按钮状态由权限和服务端状态共同决定。
8. **审计页骨架**：按时间、操作者、动作和资源筛选。

每个数据页面处理 `initial`、`loading`、`success`、`empty` 和 `error`；合规检查另处理 `UNKNOWN`、`CONFLICT` 和 `NOT_APPLICABLE`。不要使用客户端字符串解析生成概念链接，必须消费 `text_segments[]`。

## 8. Agent 边界

定义 `AgentProvider` 接口和禁用、假数据两个实现，真实供应商适配器作为可选模块。无 API 密钥时所有测试和核心业务必须通过。

Agent 仅可：组织已审核的综合文字、建议检索词、生成草稿候选。Agent 不得：创建法律事实、改变真值、发布规则、审核内容、修改法源、决定权限或直接访问数据库。所有 Agent 输出作为不可信输入再次验证，并记录模型/提示/工具版本与脱敏调用状态。

## 9. 演示数据

提供幂等种子命令，生成：

- 一个演示租户和各角色演示账号；密码只来自开发环境变量。
- 一部标记为演示的法律、两个版本、至少五个条文版本。
- 公司、董事会、审计委员会、董事、独立董事等核心概念。
- 两家公司、有效与失效任职、完整与缺失事实、证据元数据。
- 十个规则骨架及一个可执行演示规则集。
- 至少一次 `TRUE`、`FALSE`、`UNKNOWN`、`CONFLICT`、`NOT_APPLICABLE` 检查结果。

演示法律文本不得冒充正式原文；在 UI 和数据中明确显示 `DEMO / UNVERIFIED`。

## 10. 测试要求

### 10.1 后端

- 五值 `AND/OR/NOT` 真值表参数化测试。
- 半开时间区间的起点、终点、开放终点和重叠测试。
- 比例边界、缺失事实、例外、冲突和优先级测试。
- 发布门禁、自审禁止、跨租户拒绝和幂等测试。
- API 成功、校验失败、未认证、未授权、未找到和冲突测试。
- 数据库迁移从空库升级成功，并可在测试数据库重复验证。

### 10.2 前端

- 五种合规结果视觉与文本断言。
- 阅读器加载、空、错误和概念浮层交互测试。
- 权限不足时操作禁用，同时验证服务端拒绝仍被正确展示。
- 综合文本按 `text_segments[]` 渲染概念链接。

### 10.3 端到端

至少自动化覆盖 `MVP产品需求与验收标准.md` 的 AC-01 至 AC-08。若外部 Agent 未配置，AC-08 使用禁用或假 Provider 验证“无来源不补写”。

## 11. 工程与运行体验

提供以下等价命令；名称可以调整，但 README 必须给出一条龙操作：

```bash
make bootstrap   # 安装前后端依赖
make up          # 启动 PostgreSQL 等基础服务
make migrate     # 执行数据库迁移
make seed        # 写入幂等演示数据
make dev         # 启动 API 和 Web
make test        # 执行后端和前端测试
make lint        # 格式与静态检查
make e2e         # 执行核心端到端测试
make down        # 停止本地服务
```

提交 `.env.example`，不得提交真实密钥。Docker Compose 至少包含 PostgreSQL、API 和 Web，并提供健康检查。CI 至少执行格式检查、类型/静态检查、迁移验证、后端测试、前端测试和构建。

## 12. 实施顺序

按可验证的纵向切片推进，每阶段结束后更新本文件末尾状态：

1. **S0 工程初始化**：目录、依赖锁、Compose、配置、健康检查和 CI。
2. **S1 领域与数据库**：核心枚举、模型、迁移、种子和不变量测试。
3. **S2 契约与权限**：OpenAPI、认证模拟/RBAC、租户隔离和审计。
4. **S3 阅读闭环**：法律/条文/概念 API 与三栏阅读器。
5. **S4 推理闭环**：事实证据、规则引擎、五值结论和证明链。
6. **S5 审核治理**：规则状态机、双审、测试门禁和发布拒绝路径。
7. **S6 Agent 降级**：受限 Provider、确定性模板和 Eval 样例。
8. **S7 系统验收**：AC-01 至 AC-08、性能烟雾、安全测试和文档。

不要一次生成大量未经运行的代码。每个切片都先实现最小闭环，再运行相关测试；发现契约问题时同步修复前端、后端和 OpenAPI。

## 13. 明确非目标

- 不采集或发布未经人工核验的真实法规全文。
- 不宣称系统已能提供正式法律意见。
- 不实现完整生产级单点登录、计费、多区域容灾或监管报送。
- 不为“看起来完整”添加无行为的页面、接口或 `pass`/TODO 占位实现。
- 不把所有逻辑放进路由、组件或单个服务文件。
- 不跳过测试来追求目录数量或代码行数。

## 14. 完成定义

只有同时满足以下条件，才能报告 Goal 完成：

- [x] 新环境按 README 可完成安装、启动、迁移和种子导入。（在本沙箱环境完整跑通 `make bootstrap`/`alembic upgrade head`/`seed_demo.py` 的等价命令；未在另一台全新物理机上重复验证）
- [x] API 健康检查、OpenAPI 和 Web 页面均可访问。（`curl /health`、`/openapi.json`、Playwright 实际打开 Web 页面均已验证）
- [x] 数据库约束实现核心语义，迁移可从空库执行。（两次从空 schema 执行 `alembic upgrade head` 成功；CHECK/UNIQUE 约束有专门测试）
- [x] 阅读、概念、事实证据、检查和证明形成真实端到端闭环。（AC-01/02/03/04/05/06 自动化测试 + 真实 curl/浏览器走查）
- [x] 五值逻辑、时间模型、冲突处理和证明链不是占位实现。（10 条规则处理器均查询真实数据库，非硬编码）
- [x] 权限、租户隔离、双审和发布门禁由后端执行。（RBAC/租户隔离/规则治理状态机均有拒绝路径的自动化测试）
- [x] 无外部模型和真实法源也能用明确演示数据运行。（`DisabledAgentProvider` 为默认值，全部 95 个后端测试在无 Agent 情况下通过；演示数据全部标记 DEMO/UNVERIFIED）
- [x] AC-01 至 AC-08 有自动化测试或可重复验收脚本。（`tests/e2e/test_acceptance_criteria.py`，8/8 通过）
- [x] 后端、前端、构建和迁移测试全部通过。（后端 95 pytest、前端 7 vitest、`pnpm build`、`ruff`/`mypy`/`eslint`/`vue-tsc` 均绿）
- [x] README 记录架构、命令、演示账号、限制和下一步。
- [x] 没有提交密钥、真实敏感数据、虚构正式法源或静默降级。（新增 `.gitignore` 覆盖 `.venv`/`.env`；演示密码强制来自 `LAWFOCUS_DEMO_PASSWORD` 环境变量，源码中无硬编码密钥；法律文本全部标注"演示条文，非正式法律原文"）

**唯一两项未在本次会话中实际验证、诚实标注为外部阻塞**：`docker compose up`（本沙箱无 Docker 守护进程）与 GitHub Actions CI workflow 本身（未推送到真实 GitHub 仓库）。两者的配置文件均已编写，本地等价步骤已全部跑通。

## 15. Agent 工作记录

编码 Agent 在每个阶段更新下表，不得把“文件已创建”等同于“已验证”：

| 阶段 | 状态 | 验证命令/证据 | 阻塞项 |
|---|---|---|---|
| S0 | `done` | `uv sync`/`pnpm install` 成功；`uvicorn app.main:app` 本地起服务，`curl /health` 返回 200；`uv run pytest`/`ruff check .`/`mypy app` 全绿；`uv.lock`/`pnpm-lock.yaml` 已生成 | Docker 守护进程在本沙箱不可用，`docker compose up` 未实际跑通（compose/Dockerfile 已写但未执行验证）；CI workflow 未在真实 GitHub runner 上跑过 |
| S1 | `done` | 32 张表通过 `alembic upgrade head` 在本机真实 PostgreSQL 16（`lawfocus_dev`/`lawfocus_test`）从空库创建成功；`make seed` 等价的 `python -m scripts.seed_demo` 幂等（连续两次运行行数不变）；46 个 pytest 用例通过，覆盖五值 AND/OR 全真值表、半开区间、有效区间 CHECK 约束、`article`/`article_version` 唯一约束、`LegalRepositoryService` 按评价时点选版本 |  |
| S2 | `done` | JWT 登录（`POST /auth/login`）、`require_roles`/`require_tenant_access` RBAC+租户隔离依赖、统一 `{code,message,trace_id,details}` 错误结构（含请求级 trace_id 中间件）、`GET /audit-events`；53 个 pytest 通过，含跨租户拒绝、越权 403、无效/缺失 token 401、以及"403 必须落审计事件"的直接断言；`ruff check .`/`mypy app` 全绿 |  |
| S3 | `done` | `LegalRepositoryService`（精确版本+按评价时点两种寻址）、`ConceptService`（经 graph_node/graph_edge DEFINED_BY 回溯定义来源）、`SynthesisService`（确定性模板，`text_segments[]` 打概念标签）；`GET /laws`、`/laws/{code}/versions/{version}/articles/{no}`、`/laws/{code}/articles/{no}/effective`、`/concepts/{id}`、`/concepts/{id}/preview`、`/articles/{article_version_id}/synthesis` 均有 pytest 覆盖（69 个后端用例全绿）；前端三栏阅读器（`LawListView`/`ArticleReaderView`/`LegalSynthesisPanel`/`ConceptHyperlink`）用 Vitest 覆盖（7 个用例）+ 真实 Playwright 浏览器走查登录→法律列表→条文阅读→点击概念弹出定义与来源，全程针对本机真实运行的 API+Postgres+Vite dev server；走查中发现并修复一个真实 bug（synthesis 输出概念 UUID 但 concept 详情接口按 code 查找，已统一为按 id 查找并补测试） |  |
| S4 | `done` | 10 条 P0 规则处理器（`app/services/rule_handlers.py`）均查真实 DB（Organization/RoleAssignment 为权威结构注册表 → FALSE 可信；Fact 表为证据层 → UNKNOWN/CONFLICT 的真实来源）；`RuleEngine` 落 `ComplianceCheck`→`Conclusion`→`Proof`→`ProofStep` 完整证明链并支持幂等重放；`FactEvidenceService`+`POST /facts`、`/evidence`、`/facts/{id}/evidence/{id}`；81 个 pytest 全绿，含 TRUE/FALSE/UNKNOWN/CONFLICT/NOT_APPLICABLE 五值全覆盖、幂等重放、跨租户 403、证明链可查询；额外用真实运行的 API+Postgres+demo 种子数据做了活体验证：甲公司（合规）全 TRUE，乙公司真实产生 TRUE/FALSE/CONFLICT×2/UNKNOWN 混合结果，并拉取了 CONFLICT 结论的完整 proof chain 确认两条冲突 Fact 的具体取值可追溯 | GOV-CTRL-001 控制关系认定目前只有"读取 Fact 或返回 UNKNOWN"的骨架逻辑，尚无真实控制链路计算——按 GOAL 要求，GOV-TIME-001/GOV-ROLE-001 已具备真实可执行逻辑，其余规则允许通用比较器，此为符合要求的最简实现，非缺陷 |
| S5 | `done` | `RuleGovernanceService` 实现 `DRAFT→IN_REVIEW→LEGAL_APPROVED→TECH_APPROVED→PUBLISHED`+`CHANGES_REQUESTED` 状态机；`POST /rules/{id}/submit`、`/reviews`、`/publish`；发布门禁**真实重新执行**每条 `RuleTestCase`（按其 `input_facts` 引用的演示公司+评价时点调用真实规则处理器）并比对 `expected_status`，而非仅检查人工设置的布尔位；87 个 pytest 全绿，覆盖自审禁止、技术审核早于法律审核被拒、测试用例缺失/不匹配导致发布失败（并在错误体 `details.reasons` 返回具体原因）、CHANGES_REQUESTED 退回重提交、完整 happy path 到 PUBLISHED | |
| S6 | `done` | `AgentProvider` Protocol + `DisabledAgentProvider`（默认，抛 `AgentUnavailableError`）+ `FakeAgentProvider`（确定性、无网络调用）；`SynthesisService` 结构性强制边界——概念标注只在调用 Agent 之前的确定性扫描阶段发生一次，Agent 只能看到并改写纯文本片段，即使 Agent 输出把概念名字符串注入回文本也不会被追溯打标；85 个 pytest 全绿，含默认禁用回退、良性 Fake Provider 只改写纯文本、恶意 Provider 改变片段数被整体拒绝回退、恶意 Provider 注入概念名字符串但拿不到 concept_id 四类 Eval 场景 | |
| S7 | `done` | 新增 `tests/e2e/test_acceptance_criteria.py`（AC-01~AC-08 各一个真实驱动 HTTP API 的端到端用例，8/8 通过）+ `tests/e2e/test_performance_smoke.py`（按 04 号文档 §4.1"核心接口各跑 20 次"的本地烟雾检查，非官方基准）；补齐 `apps/api/.gitignore`、根 `.gitignore`（此前完全缺失，`.venv`/缓存目录处于未被忽略状态）；导出 `contracts/openapi.json`；清理误生成的 `.playwright-mcp/` 调试产物；撰写根 README（架构、快速开始、演示账号、已知限制、下一步）与 `apps/web/README.md`；修复前端 `vitest`+`vue-tsc -b` 的类型配置冲突（拆分出 `vitest.config.ts`）；最终清库重迁移重播种后完整重跑：后端 95 pytest 全绿、`ruff check .`/`mypy app` 全绿、前端 7 vitest 全绿、`pnpm build`/`pnpm lint` 全绿 | Docker 守护进程与真实 GitHub Actions runner 在本沙箱均不可用，详见 §14 完成定义下方说明 |

若因缺少外部法源、法律审核或生产凭据而无法继续，应完成不依赖该条件的工程工作，并把剩余项标记为外部阻塞；不得伪造数据或成功结果。
