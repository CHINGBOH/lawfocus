# 经济法知识图谱与上市公司治理合规推理系统 — MVP 骨架

本仓库分两层：根目录的中文规范文档定义语义/本体/规则/UI 设计（见
[CLAUDE.md](CLAUDE.md) 和 [00-项目文档索引与实施顺序.md](00-项目文档索引与实施顺序.md)），
`apps/` 下是按 [GOAL.md](GOAL.md) 实施的可运行全栈骨架。

## 架构总览

```
apps/api/   FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16（pgvector 已装，暂未使用）
apps/web/   Vue 3 + Vite + TypeScript + Vue Router + Pinia + Vitest
contracts/  导出的 OpenAPI 契约（apps/api 每次改动后可重新导出）
```

六层能力映射到代码：

| 层 | 代码位置 |
|---|---|
| 法律仓库 / 版本 | `app/models/legal.py`、`app/services/legal_repository_service.py` |
| 知识图谱（概念/关系） | `app/models/graph.py`、`app/services/concept_service.py` |
| 治理主体/角色/事件 | `app/models/governance.py` |
| 事实/证据 | `app/models/facts.py`、`app/services/fact_evidence_service.py` |
| 规则治理（提交/审核/发布） | `app/models/rules.py`、`app/services/rule_governance_service.py` |
| 规则执行 | `app/services/rule_handlers.py`（10 条 P0 规则）、`app/services/rule_engine.py` |
| 推理结果 / 证明链 | `app/models/inference.py` |
| 五值逻辑 / 时间区间（不依赖数据库的核心不变量） | `app/domain/truth.py`、`app/domain/time_interval.py` |
| Agent 边界 | `app/services/agent_provider.py`、`app/services/synthesis_service.py` |
| 审计 / RBAC / 租户隔离 | `app/services/audit_service.py`、`app/services/authorization_service.py`、`app/api/v1/deps.py` |

前端三栏阅读器：`apps/web/src/views/ArticleReaderView.vue` + `LegalSynthesisPanel.vue` + `ConceptHyperlink.vue`。

## 快速开始

前置：本机已安装 PostgreSQL 16（含 pgvector 扩展也可，非必需）、`uv`、Node 22+、`pnpm`（或 `corepack enable && corepack prepare pnpm@latest --activate`）。

```bash
make bootstrap   # 安装前后端依赖（uv sync + pnpm install）

# 手动创建数据库角色和库（本仓库未附带自动化的本地 Postgres 初始化脚本）：
#   CREATE ROLE lawfocus LOGIN PASSWORD 'lawfocus_dev_password';
#   CREATE DATABASE lawfocus_dev  OWNER lawfocus;
#   CREATE DATABASE lawfocus_test OWNER lawfocus;

make migrate     # alembic upgrade head（对 lawfocus_dev）
LAWFOCUS_DEMO_PASSWORD='选一个开发用密码' make seed
make dev         # 同时起 API (:8000) 和 Web (:5173)
```

浏览器打开 `http://localhost:5173`，使用下方演示账号登录。

也可以用 `docker compose up`（`docker-compose.yml` 已提供 db/api/web 三个服务）——**本沙箱开发环境没有可用的 Docker 守护进程，因此 compose 路径未被实际跑通验证过**，请在有 Docker 的机器上验证。

## 测试

```bash
make test   # 后端 pytest（对 lawfocus_test）+ 前端 vitest
make lint   # ruff + mypy + eslint + vue-tsc
make e2e    # 仅端到端用例（AC-01..AC-08 + 性能烟雾）
```

当前状态（本机真实运行验证）：后端 95 个 pytest 全绿，`ruff check .` / `mypy app` 全绿；前端 7 个 vitest 全绿，`pnpm build` / `pnpm lint` 全绿。

## 演示账号

`LAWFOCUS_DEMO_PASSWORD` 环境变量指定的密码对以下所有账号生效（种子脚本不接受硬编码密码）：

| 邮箱 | 角色 |
|---|---|
| reader@demo.lawfocus | Reader |
| compliance@demo.lawfocus | ComplianceUser（demo-tenant） |
| editor@demo.lawfocus | KnowledgeEditor（demo-tenant） |
| legal-reviewer@demo.lawfocus | LegalReviewer |
| tech-reviewer@demo.lawfocus | TechnicalReviewer |
| publisher@demo.lawfocus | Publisher |
| auditor@demo.lawfocus | Auditor |
| admin@demo.lawfocus | SystemAdmin |

演示数据（`apps/api/scripts/seed_demo.py`，幂等，可重复执行）：一部标记 `DEMO/UNVERIFIED` 的合成法律（非真实法条）、两个法律版本、5 个条文的双版本文本、4 个核心概念（含图谱溯源边）、两家演示公司——甲公司治理结构完整合规，乙公司故意缺失审计委员会、独立董事比例不足、任职已过期、且对同一事实存在两条互相矛盾的记录，用于真实产出 TRUE/FALSE/UNKNOWN/CONFLICT 四类结果（NOT_APPLICABLE 由非上市公司主体触发，测试中覆盖，演示种子未包含非上市公司）。

## 已知限制 / 未完成项

- **无真实法源**：所有法律/条文/概念/规则数据均为合成演示数据，标记 `DEMO`/`UNVERIFIED`，不构成真实法律依据。首批真实法源的采集、哈希登记与法律审核需要人工完成（见 [01-MVP权威法源与版本清单.md](01-MVP权威法源与版本清单.md)）。
- **10 条规则未绑定正式法条**：当前 `rule_source` 指向的是演示条文，规则版本停留在 `DRAFT`，无法通过正式发布门禁（符合 GOAL.md §6 的明确要求，不是缺陷）。
- **GOV-CTRL-001（控股股东/实际控制人认定）** 目前只有"读取 Fact 或返回 UNKNOWN"的骨架逻辑，没有真实的控制链路计算——按 GOAL.md 的要求，只有 GOV-TIME-001/GOV-ROLE-001 必须具备真实逻辑，其余规则允许通用比较器。
- **Docker Compose 路径未验证**：本开发沙箱没有可用的 Docker 守护进程，`docker-compose.yml`/两个 `Dockerfile` 已编写但从未实际 `docker compose up` 过，请在有 Docker 的环境中验证。
- **CI workflow 未在真实 GitHub Actions runner 上跑过**：`.github/workflows/ci.yml` 已配置（含真实 PostgreSQL service container），本地等价步骤（migrate/pytest/ruff/mypy/vitest/build）均已跑通，但只有推送到真实 GitHub 仓库后才能验证 workflow 本身。
- **性能验证仅为本地烟雾测试**：`tests/e2e/test_performance_smoke.py` 只是按 04 号文档 §4.1 的"核心接口各跑 20 次"跑通，不是官方基准（官方基准需要该文档 §2 规定的大规模数据集和独立环境）。
- **Agent 只有 Disabled/Fake 两种实现**：真实 LLM Provider 适配器留作可选扩展点（`app/services/agent_provider.py`），当前无 API 密钥也能通过全部测试和核心业务流程。
- **`contracts/openapi.json`** 是某次 `apps/api` 运行的快照，模型变更后需要重新导出（见下方命令）。

重新导出 OpenAPI 契约：

```bash
cd apps/api && uv run python -c "
import json
from app.main import app
json.dump(app.openapi(), open('../../contracts/openapi.json', 'w'), ensure_ascii=False, indent=2)
"
```

## 下一步建议

1. 法律知识工程师按 `01-MVP权威法源与版本清单.md` 采集首批真实法源并完成哈希登记。
2. 法律审核者逐条把 `02-上市公司治理MVP十条规则清单.md` 的规则绑定到已验证的真实条文版本，走完 submit → 双审 → publish 流程。
3. 在有 Docker 的环境验证 `docker compose up` 全链路，并把 CI workflow 推到真实 GitHub 仓库跑一遍。
4. 视需要接入真实 Agent Provider（继承 `AgentProvider` 协议），仍需保持"Agent 不可用时核心业务照常运行"的降级路径。
5. 补充 `04-MVP性能基准与容量验收方案.md` 要求的正式基准数据集和负载测试。
