# Database migrations

Alembic is the only executable database migration entry point. The SQL file in
`contracts/db` remains a comparison contract and must never be executed.

Review before running, then apply explicitly:

```powershell
python -m alembic upgrade head
```

现有 revision（0001–0005）均有 `downgrade`。0005 在存在两个及以上账号时明确拒绝回滚，防止不同用户的数据静默混合；仅空库或可安全合并的单账号状态可往返。回滚会删除本次迁移创建的表/列及其中数据，必须先备份并由人审查目标 revision；不要对用户库运行往返测试。0002 回滚保留 0001 已拥有的 `list_url/boss_name/company_desc`。

0005 升级兼容早期现有库的 `raw_job_source_id_ext_id_key` 与当前 0001 定义的 `uq_raw_job_source_ext_id` 两种同列唯一约束名；迁移会核对约束列，其他未知形态仍拒绝。降级后统一恢复为 `uq_raw_job_source_ext_id`。

隔离验证仅在**新建、空的** `jobos_migration_test` 数据库执行：设置该库的 `DATABASE_URL` 与 `RUN_MIGRATION_ROUNDTRIP=1` 后运行 `python -m pytest tests/migration/test_roundtrip.py`。测试先检查数据库名和空库，再执行 `base → head → 0001 → base → head`，并检查多账号拒绝回滚；它会删除测试库业务表，不得指向用户数据。

生产顺序仍为备份 → 迁移检查 → 基础设施 → Alembic 迁移 → 服务升级。API 启动不会自动执行 DDL。
