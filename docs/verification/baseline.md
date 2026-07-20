# R0 基线报告

- 日期：2026-07-18 01:30 CST（本机）
- 父工作树 HEAD：`bcb4a33`（`/home/l/projects`；lawfocus 目录整体被父仓库 `.gitignore` 的 `/*` 规则忽略，未纳入版本跟踪）
- 环境：本机 PostgreSQL 16（localhost:5432），`lawfocus_dev` / `lawfocus_test` 两库均在迁移 `e97de187ca96 (head)`

## 命令与实测结果

| 命令 | 结果 |
|---|---|
| `cd apps/api && uv run pytest` | **120 passed**，37.15s（1 个无害警告：starlette TestClient 弃用提示） |
| `cd apps/web && pnpm test` | **13 passed / 5 files**，1.19s；存在 1 个既有 `[Vue Router warn]: No match found for location with path "/"`（出自 `tests/AuditView.test.ts` 的 403 用例），列入 R2 消除项 |
| `cd apps/api && uv run ruff check .` | All checks passed |
| `cd apps/api && uv run mypy app` | Success: no issues found in 63 source files |
| `cd apps/web && pnpm lint`（eslint + vue-tsc --noEmit） | 通过 |
| `cd apps/web && pnpm build` | ✓ built in 641ms |
| `cd apps/api && uv run alembic current`（dev 与 test 库分别执行） | 均为 `e97de187ca96 (head)` |
| OpenAPI 漂移检查：`app.openapi()` 与 `contracts/openapi.json` 规范化 JSON 逐字节比较 | **MATCH（无漂移）** |

## 工作树卫生

- `git status --short`（lawfocus 目录）：无任何条目；该目录全部内容被父仓库忽略，`.env`、数据库、浏览器缓存、截图、trace 不存在"意外提交"路径。
- 父工作树现存改动全部属于兄弟项目 `experiments/english-learning-repository/`，与 lawfocus 无关，本工作包未触碰。
- 根目录存在 `.playwright-mcp/`（此前浏览器走查的缓存目录），同样被父仓库忽略；R3 接入 Playwright 时按 07 指南另行管理 trace/截图。

## 与文档旧数字的差异

- `README.md` 中"后端 95 pytest / 前端 7 vitest"已过时，实测为 **120 / 13**（与 AGENTS.md 记录一致）。

## R0 退出条件核对

- [x] 当前主流程测试全部通过（后端 120、前端 13）
- [x] `contracts/openapi.json` 与 `app.openapi()` 完全一致
- [x] 工作树中没有意外提交 `.env`、数据库、浏览器缓存、截图或 trace
- [x] 基线命令和结果写入本文件

另完成 07 指南 §2.1：`06-MVP骨架充实与功能闭环计划.md` 工作记录末尾重复的 `F6` 行已删除（指南原文为"将第二个改为 F7"，但表中本已存在 F7 行，直接删除重复行才达成 F6/F7 各一行的意图；未改动任何状态字段）。
