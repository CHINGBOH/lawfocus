# A3：数据治理§7上线验收前4项 — 核实结果

- 日期：2026-07-19（本机）
- 依据：`05-真实公司材料数据治理规范.md` §7

## 逐项结果

| 验收项 | 状态 | 证据 |
|---|---|---|
| 跨租户访问对抗测试 | **已通过** | `tests/integration/test_auth_and_rbac.py::test_tenant_scoped_auditor_cannot_read_a_different_tenant`、`tests/integration/test_facts_evidence.py::test_link_rejects_evidence_from_a_different_tenant` 均已覆盖并通过 |
| 跨租户导出对抗测试 | **不适用（功能不存在）** | 全仓库搜索确认当前没有任何"导出"接口（`app/api/v1/*.py` 无 export/download 路由）——不是漏测，是导出功能本身尚未实现，无法对抗测试一个不存在的功能。待导出功能上线后需补测 |
| 开发/测试环境隔离 | **已验证** | `apps/api/tests/conftest.py` 硬连 `lawfocus_test`，与 `lawfocus_dev` 物理分库；本次另建 `lawfocus_restore_drill` 三库互不干扰 |
| 生产环境隔离 | **不适用（无生产环境）** | 本沙箱未部署任何生产实例，无法验证"生产隔离"，如实标注而非假装已验证 |
| 备份恢复演练 | **已完成，本机实测** | 见下 |
| 脱敏规则演练 | **未演练** | 当前无真实 CONFIDENTIAL/RESTRICTED 材料入库（仅 PUBLIC 级公司法+年报+新导入的5个监管/交易所规则），脱敏规则暂无真实数据可供演练 |
| 密钥轮换演练 | **未演练** | 本沙箱无密钥管理基础设施（无 KMS/Vault），无可轮换对象 |
| 数据目录、分级责任人登记 | **未登记（组织性决定，非工程可解决）** | 需要产品/数据保护责任人指定具体人员和登记流程，不应由 Agent 代为拍板或虚构责任人姓名 |

## 备份恢复演练详情

```bash
pg_dump -h localhost -U lawfocus -d lawfocus_dev -F c -f lawfocus_dev_backup.dump
# 新建非生产库 lawfocus_restore_drill（postgres 超级用户创建，lawfocus 角色无 CREATEDB 权限）
pg_restore -h localhost -U lawfocus -d lawfocus_restore_drill lawfocus_dev_backup.dump
```

恢复后核对结果（源库 vs 恢复库，逐表比对）：

| 表 | 源库 | 恢复库 |
|---|---:|---:|
| legal_version | 8 | 8 |
| article | 1756 | 1756 |
| rule_set_member | 4 | 4 |
| fact_evidence | 6 | 6 |
| compliance_check | 6 | 6 |
| audit_event | 73 | 73 |

另验证恢复库的外键关联（`article` join `legal_document`，7 个法律文档条数分布：公司法266 + 治理准则101 + 独董办法48 + 上交所规则521 + 上交所指引295 + 深交所规则520 + 演示公司法5）与 `alembic_version`（`e97de187ca96`）均正确保留。演练完成后 `lawfocus_restore_drill` 库与临时备份文件已清理，不留存。

## 结论

四项中真正可由工程验证的两项（跨租户对抗测试、备份恢复演练）已完成并通过；导出对抗测试因功能未实现而不适用；环境隔离仅能验证到"开发/测试"这一级，生产环境隔离因无生产部署而不适用；数据目录责任人登记、脱敏规则演练、密钥轮换演练均需要真实组织决策或真实敏感数据才能进行，如实标记为未完成，不得虚构责任人或伪造演练记录冒充已验收。
