# AGENTS.md

> 本文件面向 AI 编码 Agent：假设读者对本项目一无所知。阅读后应能正确理解架构、运行命令、代码约定与不可违反的领域语义。

## 1. 项目概览

本仓库是 **「经济法知识图谱与上市公司治理合规推理系统」**（lawfocus），分两层：

1. **规范文档层**（根目录的中文 Markdown）：定义形式化语义、本体、规则数据结构、数据库/图谱设计、UI 设计与 MVP 验收基线。`00-项目文档索引与实施顺序.md` 是文档索引与权威阅读顺序入口；`法律形式化元模型与精确语义规约.md` 是最高权威规范，一切代码与其他文档不得与之冲突。阅读顺序：`00` → 核心五篇（形式化元模型、对象与关系词典、规则数据结构设计、数据库与图谱设计、UI 功能设计）→ `MVP产品需求与验收标准.md` 与 `01`–`05` 五份基线。
2. **可运行的 MVP 全栈骨架**（`apps/`）：按 `GOAL.md`（编码 Agent 的执行目标，含 12 条不可违反的领域语义与分阶段完成记录）实施，`README.md` 记录了架构映射、快速开始、演示账号与已知限制。

修改任何类型、关系或规则字段时，必须同步检查所有受影响的规范文档与代码；传播规则见 `00-项目文档索引与实施顺序.md` §4。

## 2. 目录结构与代码组织

```
apps/api/          后端：FastAPI + SQLAlchemy 2 + Alembic（Python ≥ 3.12，uv 管理）
  app/
    api/v1/        路由层：auth/laws/articles/concepts/facts/compliance/rules/rulesets/subjects/audit
    core/          配置（pydantic-settings，LAWFOCUS_ 前缀）、数据库会话、JWT 安全、统一错误结构
    domain/        不依赖数据库的核心不变量：五值真值（truth.py）、半开时间区间、规则结果
    models/        SQLAlchemy 模型：legal / graph / governance / facts / rules / inference / identity / audit
    schemas/       Pydantic 请求/响应模型
    services/      业务服务：法源仓库、概念、事实证据、规则引擎、规则治理、RBAC、审计、小综合、Agent 边界
    repositories/  数据访问层
  migrations/      Alembic 迁移（versions/ 下已有 2 个迁移脚本）
  scripts/         seed_demo.py（幂等演示种子）
  tests/           unit（纯领域逻辑）/ integration（服务+API）/ e2e（AC-01..08 + 性能烟雾）
apps/web/          前端：Vue 3 + Vite + TypeScript + Vue Router + Pinia（pnpm 管理）
  src/views/       页面：三栏条文阅读器、合规检查向导/结果、规则中心、事实证据、审计等
  src/components/  ConceptHyperlink.vue、LegalSynthesisPanel.vue（小综合面板）
  src/api/         API client；src/stores/ Pinia；src/types/ 类型（含契约镜像类型）
  tests/           Vitest 组件/视图测试
contracts/openapi.json   导出的 OpenAPI 契约快照（API 模型变更后须重新导出，命令见 README.md）
.github/workflows/ci.yml GitHub Actions CI
docs/、scripts/、data/demo/   预留目录，目前为空
```

六层能力到代码的映射（法源仓库/图谱/治理主体/事实证据/规则治理与执行/证明链，以及 RBAC、租户隔离、Agent 边界）详见 `README.md` 的架构总览表。

## 3. 技术栈

- **后端**：Python ≥ 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、psycopg 3、python-jose（JWT）、bcrypt；开发依赖 pytest、pytest-asyncio、httpx、ruff、mypy。包管理用 **uv**（`uv.lock` 已提交，`uv sync` 安装）。
- **前端**：Vue 3、Vite、TypeScript、Vue Router、Pinia；测试 Vitest + @vue/test-utils + jsdom；lint 用 eslint（flat config）+ vue-tsc。包管理用 **pnpm**（`pnpm-lock.yaml` 已提交）。
- **数据库**：PostgreSQL 16（docker 镜像 `pgvector/pgvector:pg16`，pgvector 已装但暂未使用；全文检索用 PostgreSQL FTS）。图结构暂用 `graph_node`/`graph_edge` 关系表，**第一阶段明确不引入** Neo4j、Z3、Celery、Kubernetes 或微服务（GOAL.md §2）。
- **运行架构**：单体 FastAPI（:8000，`/api/v1` 前缀）+ Vite dev server（:5173）+ PostgreSQL（:5432）；`docker-compose.yml` 提供 db/api/web 三服务（**compose 路径未实际验证过**，本开发沙箱无 Docker 守护进程）。
- **Agent**：`AgentProvider` 协议 + `DisabledAgentProvider`（默认）+ `FakeAgentProvider`，由 `LAWFOCUS_AGENT_PROVIDER` 配置；真实 LLM 适配器是可选扩展点，无密钥时全部测试与核心流程必须通过。

## 4. 构建、运行与测试命令

根目录 `Makefile` 提供一条龙命令：

```bash
make bootstrap   # uv sync（后端）+ pnpm install（前端）
make up          # docker compose up -d db（需 Docker；无 Docker 时手动建库，见 README）
make migrate     # cd apps/api && uv run alembic upgrade head
make seed        # 幂等演示种子；需 LAWFOCUS_DEMO_PASSWORD 环境变量（不接受硬编码密码）
make dev         # 同时起 API (:8000) 和 Web (:5173)
make test        # 后端 pytest（连 lawfocus_test 库）+ 前端 vitest
make lint        # ruff check + mypy app（后端）；eslint + vue-tsc --noEmit（前端）
make e2e         # 仅端到端：tests/e2e（AC-01..AC-08 + 性能烟雾）
make down        # docker compose down
```

常用单端命令：

```bash
cd apps/api && uv run pytest                 # 后端全部测试（需本机 PostgreSQL + lawfocus_test 库）
cd apps/api && uv run pytest tests/e2e       # 仅验收/性能端到端
cd apps/api && uv run uvicorn app.main:app --reload --port 8000
cd apps/web && pnpm dev / pnpm test / pnpm build / pnpm lint
```

**重要前提**：后端测试不是 SQLite/内存库——`apps/api/tests/conftest.py` 硬连本机 `localhost:5432` 的 `lawfocus_test` 库（账号 `lawfocus`/`lawfocus_dev_password`）。需先手动 `CREATE ROLE`/`CREATE DATABASE lawfocus_dev`/`lawfocus_test` 并对测试库执行 `alembic upgrade head`（命令见 `README.md`）。测试在外层事务 + SAVEPOINT 中运行并回滚，不会污染数据，但模式必须已迁移。

## 5. 代码与文档风格约定

- **文档语言为中文**；代码标识符、schema 字段、组件名用英文（`PascalCase` / `snake_case`）。规范文档用 Markdown + LaTeX 块（`\[ ... \]`）承载形式化公式，公式是规范内容本体，编辑时不得丢失；新增文档沿用描述性中文文件名 + UTF-8。
- **后端**：ruff（line-length 120，`E,F,I,UP,B` 规则集，排除 `migrations/versions`）+ mypy（`app/` 目录）必须全绿。分层：路由只做参数解析与鉴权委托，业务在 services，纯领域不变量在 `app/domain/`（不依赖数据库），不在路由/组件里堆逻辑。
- **前端**：eslint flat config + `vue-tsc --noEmit` 必须全绿；关闭了若干仅样式性的 vue 规则（见 `eslint.config.js` 注释）。组件命名沿用 UI 设计文档 §17 的既定名称（`ArticleReader`、`ConceptHyperlink`、`LegalSynthesisPanel` 等），不要另造名字。概念链接必须消费后端 `text_segments[]` 分段结构渲染，禁止客户端字符串解析。
- 每个数据页面处理 `initial/loading/success/empty/error` 五态；合规结果另处理 `UNKNOWN/CONFLICT/NOT_APPLICABLE`。
- 配置走环境变量：`LAWFOCUS_*`（后端，`apps/api/.env.example`）、`VITE_API_BASE_URL`（前端）；只提交 `.env.example`，**禁止提交真实密钥**（根与 `apps/api/` 的 `.gitignore` 已覆盖 `.env`/`.venv`）。

## 6. 不可违反的领域语义（写任何代码/文档前必须内化）

摘自 `GOAL.md` §4 与 `CLAUDE.md`，与形式化元模型规约冲突时以后者为最高依据：

1. 自然人 / 角色 / 任职 / 事件分离：禁止 `Director(person)`，必须用带有效区间的 `RoleAssignment`；持续关系（`Controls`）与一次性事件（`VoteEvent`）分开。
2. 法律文本 / 概念 / 可执行规则分离：每个已发布规则必须关联 `ArticleVersion` 溯源；**法源原文与已发布内容只增新版本，绝不原位覆盖（append-only）**。
3. 事实 / 证据 / 结论分离：结论必须带证明链（`Conclusion ⇒ ∃p: Proves(p,c)`）。
4. 真值固定为五值 `TRUE | FALSE | UNKNOWN | CONFLICT | NOT_APPLICABLE`，**不得退化为布尔**；缺失记录是 `UNKNOWN` 而非 `FALSE`（开放世界假设）。
5. 动态关系一律用半开区间 `[valid_from, valid_to)`；交易时间与有效时间分离。
6. 规则冲突按 `(Authority, Specificity, ExceptionLevel, TemporalOrder)` 字典序消解；无法消解的同秩冲突必须输出 `CONFLICT`，不得静默择一。
7. 模型置信度与法律真值分开存储；Agent 输出是不可信输入，必须重新验证，不得直接成为已审核事实或规则；Agent 只能改写纯文本、不得引入新法律命题（结构性强制，见 `app/services/synthesis_service.py`）。
8. **所有租户私有查询必须由后端强制 `tenant_id` 过滤**；RBAC、自审禁止（提交人不得做自己版本的法律审核人）、双审（LegalReviewer + TechnicalReviewer）+ 测试全绿才能发布，均由后端真实执行。
9. 比例计算用整数交叉相乘的确定性算法；数量/比例为精确比较。
10. 演示数据一律标记 `DEMO / UNVERIFIED`，不得伪装成正式法律内容；真实公司材料默认排除（数据分级见 `05-真实公司材料数据治理规范.md`）。

## 7. 测试策略

- **后端 pytest**（`asyncio_mode = "auto"`）：`tests/unit/` 覆盖纯领域逻辑（五值 AND/OR/NOT 参数化真值表、半开时间区间）；`tests/integration/` 覆盖服务与 API（模式不变量/CHECK 约束、认证与 RBAC、租户隔离 403、规则治理状态机与发布门禁、合规检查五值全覆盖、幂等重放、Agent 边界 Eval 场景等）；`tests/e2e/` 覆盖 `MVP产品需求与验收标准.md` 的 AC-01..AC-08 与性能烟雾（按 04 号文档 §4.1 的本地口径，非官方基准）。规则用例须覆盖通过/违反/边界/缺失事实/不适用，例外与冲突在规则集层覆盖。当前基线（2026-07 本机实测）：**120 个后端用例全绿**（约 37 秒）。
- **前端 Vitest**（jsdom）：五种合规结果的视觉/文本断言、阅读器交互、`text_segments[]` 渲染等，当前 **5 个文件 13 个用例全绿**。
- 注意：`README.md` 中"后端 95 pytest / 前端 7 vitest"的数字已过时（此后又新增了用例）；以实际运行结果为准。
- **交叉一致性是文档层的"测试"**：改规范后用 `rg 'RoleAssignment|TruthValue' *.md` 之类检查跨文档术语；`git diff --check` 查空白错误。
- **发布门禁本身会真实重跑测试用例**：`POST /rules/{id}/publish` 会按每条 `RuleTestCase` 的输入真实调用规则处理器并比对 `expected_status`，不是检查人工布尔位。
- 不得跳过测试追求代码量；不得把"文件已创建"当作"已验证"（GOAL.md §15 的工作记录表区分这两者）。

## 8. 安全注意事项

- 源码中不得出现硬编码密钥；演示账号密码只来自 `LAWFOCUS_DEMO_PASSWORD` 环境变量（种子脚本强制要求）。
- 统一错误结构为 `{code, message, trace_id, details?}`，**不得**把堆栈、SQL、密钥或敏感证据返回客户端（`app/core/errors.py`）。
- 所有写接口必须验证身份、权限、对象版本与业务不变量；`POST /compliance-checks` 支持 `Idempotency-Key` 幂等。
- 高风险操作（发布、拒绝、导出等）必须落 `audit_event` 审计（追加式，含操作者/动作/资源）；越权 403 也要落审计。
- Agent 输出按不可信输入处理：记录模型/提示/工具版本与脱敏调用状态；Agent 无数据库直连权限。
- 真实公司材料按 `PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED` 分级管理；`INTERNAL` 以上需数据责任人+DPO 批准，开发/CI 只用合成或不可逆匿名化数据。

## 9. CI 与部署

- `.github/workflows/ci.yml`：api job（pgvector/pgvector:pg16 service container + `uv sync` + ruff + mypy + `alembic upgrade head` + pytest）与 web job（Node 22 + corepack/pnpm + lint + test + build）。**该 workflow 尚未在真实 GitHub runner 上跑过**，本地等价步骤均已验证。
- `docker-compose.yml` 含 db/api/web 三服务与健康检查；`apps/api/Dockerfile`、`apps/web/Dockerfile` 已编写，但 **compose 全链路未实际验证**（本沙箱无 Docker 守护进程），在有 Docker 的机器上验证前不要宣称可用。
- API 模型变更后需重新导出 `contracts/openapi.json`（导出命令见 `README.md`）。

## 10. 已知限制（诚实状态，详见 README.md §已知限制）

- 无真实法源：所有法律/条文/概念/规则均为合成演示数据（`DEMO/UNVERIFIED`）；10 条 P0 规则的 `rule_source` 指向演示条文、版本停留在 `DRAFT`，无法通过正式发布门禁（符合 GOAL.md §6 的设计，非缺陷）。
- `GOV-CTRL-001` 只有"读 Fact 或返回 UNKNOWN"的骨架逻辑；按 GOAL.md 仅 `GOV-TIME-001`/`GOV-ROLE-001` 必须具备真实逻辑。
- 性能验证仅为本地烟雾测试，非 04 号文档的正式基准。
- 版本提示：本目录处于父目录 `/home/l/projects` 的 git 工作树内（非独立仓库），`git status` 会显示兄弟目录的改动——不要误操作其他项目的文件。
