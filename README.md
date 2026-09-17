# AI Resume OS / JobOS

本地单机求职工作台。当前代码已包含配对与 WS Gateway、被动岗位采集/导入、岗位池补全队列、筛选池流转、人工候选决策和三主题控制台；Stage-0 规则筛选、JD 解析/匹配、简历/投递包、聊天回采与复盘仍未实现。代码进度不等于阶段出口验收，详见[项目状态快照](docs/delivery/06-项目状态快照.md)。

最新提交信息称 v0.3.0，扩展清单版本也是 0.3.0；仓库当前没有对应 Git tag，根包和 Python 包仍为 0.1.0，不应把提交标题视为已完成发布验收。

## Architecture references

- `ARCH-MOD-001`: FastAPI modular monolith with isolated workers.
- `ARCH-SEC-001`: loopback-only host boundary.
- `ARCH-DEP-001`: local Docker Compose topology.
- `ARCH-CONTRACT-001`: documents define semantics; `contracts/` defines shape.
- `ARCH-AIAGENT-001`: contract-first changes, negative safety tests, human review.

## Toolchain

- Node.js 20 and pnpm 9
- Python 3.12
- Docker Desktop with Docker Compose

The repository pins these baselines in `.nvmrc`, `.python-version`, `package.json`, and the Dockerfiles. Host versions outside the baseline may inspect the project, but verification evidence must come from the pinned runtimes.

## Local setup

1. Copy `config/.env.example` to `.env`.
2. Replace the sample PostgreSQL password and leave secret values out of source control.
3. Run `docker compose config` to inspect the resolved local topology.
4. 先运行 `docker compose up -d postgres redis`。
5. 检查备份与迁移计划后，显式运行 `docker compose run --rm --no-deps api python -m alembic upgrade head`。服务启动不会自动迁移数据库。
6. 运行 `docker compose up -d --build api worker worker-renderer web`。
7. 打开 `http://127.0.0.1:4173`。

公开端口显式绑定 `127.0.0.1`。扩展必须在选项页人工填写本机 WS 地址与配对码；配对码来自本机 `data/config/pairing.token`，控制台不会回显。仓库内扩展为岗位池详情/公司补全桥，列表采集依赖外部只读的 boss-helper 扩展，真实端到端验收仍待人审。

## Verification

```text
pnpm test
pnpm typecheck
pnpm build
python -m pytest
ruff check services tests
black --check services tests
mypy services
```

请用 Node 20 / pnpm 9 / Python 3.12 复验。迁移双向往返测试仅能在空的 `jobos_migration_test` 隔离库中显式启用，步骤见[迁移说明](migrations/README.md)。测试样本必须是合成数据；不要把真实账号、聊天、密钥写入仓库。
