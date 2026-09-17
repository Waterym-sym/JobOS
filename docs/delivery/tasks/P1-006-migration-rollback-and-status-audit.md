# P1-006 迁移回滚与项目状态文档对齐

```yaml
task: P1-006-migration-rollback-and-status-audit
status: ready_for_human_review
domain_owner: Data Platform / Delivery
architecture_refs:
  - ARCH-DATA-001
  - ARCH-CONTRACT-001
  - ARCH-API-001
  - ARCH-EXT-001
  - ARCH-AIAGENT-001
contracts:
  - contracts/db/0001_baseline.skeleton.sql
  - contracts/api/openapi.yaml
  - contracts/ws/protocol.schema.json
data_classification: internal
human_approval: required
nfr:
  - Alembic 是唯一数据库迁移入口
  - 只在隔离测试库验证 downgrade，不回滚用户数据
  - 进度以当前代码、测试及人工评审证据为准
acceptance_tests:
  - 四个已存在 revision 在空库可完成 base→head→base→head
  - 0002 downgrade 不删除 0001 已拥有的列
  - 新迁移模板不得默认生成仅前滚代码
  - README、迁移、交付状态文档不再声称采集未实现或仅前滚
red_lines:
  - AGENTS.md 禁止项 1、4、5、8、10
  - 不修改 ADR、AGENTS.md、24 篇红线或验收阈值
  - 不将任务合入 main 等同于阶段出口验收
```

## DoR 与裁决

- 2026-09-17：本人明确裁决“必须支持 downgrade”，消除交付验收与迁移实现的冲突。
- 架构检索：ARCH-DATA-001 要求 Alembic 唯一入口及可前滚；ARCH-CONTRACT-001 要求契约先行；交付物清单和测试策略要求 upgrade/downgrade 双向通过。
- 本任务不变更机器契约形状，只补迁移逆操作、负向保护测试和状态文档。
- DDL/迁移属于 🟡 人审；完成后保持待人工 Review。

## 范围

1. 四个已存在 Alembic revision 的逆操作。
2. 独立数据库双向往返验证与默认测试门禁。
3. README、迁移说明、交付状态及相关任务单的时效性更新。
4. 新迁移模板改为要求实现并测试 downgrade 的显式占位。

## 非范围

- 真实生产库或用户库回滚。
- 修改架构 ADR、AGENTS.md、24 篇红线及验收阈值。
- 新增业务能力、自动对外动作或真实账号自动化。

## 验证与自评（2026-09-17）

- 隔离、空的 PostgreSQL `jobos_migration_test`：`base → head → 0001 → base → head` 往返通过（1 passed）；核对 0002 不删除 0001 列、回到 base 后业务表及相关 enum 消失、可重新升级。临时数据库容器已停止。
- Python 3.12 默认测试：161 passed、7 skipped；迁移往返需显式开关，默认不会碰用户库。
- 本次迁移文件与测试的 Ruff 通过；全量 Ruff 仍有 8 处存量风格问题，全量 mypy 仍有 17 处存量类型错误，详见 [状态快照](../06-项目状态快照.md)。
- Web/扩展测试、类型检查与构建在本机 Node 24 快速回归通过，仍须按项目 Node 20 基线复核。
- 自评：只修改已存在迁移的逆操作与模板，不更改 schema 契约或前向 DDL；回滚会删数据，未在用户库执行。🟡 迁移和文档结论仍待独立人工 Review，未合并、未发布、未标记阶段通过。
