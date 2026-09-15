# P1-001 本地 Monorepo 框架

```yaml
task: P1-001-local-monorepo-scaffold
status: ready_for_human_review
domain_owner: Platform
architecture_refs:
  - ARCH-MOD-001
  - ARCH-SEC-001
  - ARCH-NFR-001
  - ARCH-DEP-001
  - ARCH-CONTRACT-001
  - ARCH-AIAGENT-001
contracts:
  - contracts/ws/protocol.schema.json
  - contracts/ws/commands.schema.json
  - contracts/ws/events.schema.json
  - contracts/ws/raw-job.schema.json
  - contracts/ws/chat-event.schema.json
  - contracts/api/openapi.yaml
  - contracts/db/0001_baseline.skeleton.sql
data_classification: internal
human_approval: required
nfr:
  - 本机 CRUD P95 不高于 300ms
  - 非 loopback 入站 100% 拒绝
  - restricted 数据第三方外发为 0
  - 自动对外动作代码路径为 0
acceptance_tests:
  - 根目录结构与专题 23 §2 一致
  - Node 20、pnpm 9、Python 3.12 版本门禁可复现
  - Compose 暴露端口全部显式绑定 127.0.0.1
  - API、Web、Worker 和 Renderer 均有独立健康检查
  - 配置校验拒绝非 loopback 绑定、低于风控下限的延迟和大于 1 的采集并发
  - 契约测试直接读取 contracts 机器真源
  - 安全扫描证明不存在 AGENTS.md 禁止清单中的对外动作路径
red_lines:
  - AGENTS.md 禁止项 1-10 全部适用
  - 不修改 ADR、验收阈值或既有红线
  - 不手改 packages/contracts-py 或 packages/contracts-ts 生成物
```

## 目标

建立专题 23 §2 规定的最小可运行 Monorepo 骨架，为 P1 后续配对鉴权、WS Gateway、扩展重写和数据库迁移提供稳定基线。本任务不实现采集、填充、聊天解码、事实生成或任何对外动作。

## DoR 审计（2026-09-15）

| 检查项 | 当前证据 | 结论 |
|---|---|---|
| 23/24 篇已人工评审 | Owner 于 2026-09-15 在任务会话中明确授权 | 通过 |
| WS 契约已由 `v0-draft` 冻结为 `v1` | 五份 WS Schema 均为 `v1`，契约加载与 Gold Case 通过 | 通过 |
| OpenAPI 核心路径骨架确认 | `contracts/api/openapi.yaml` 已冻结为 `1.0.0 / v1` | 通过 |
| 规则边界集 v0 | `tests/fixtures/rules/filter-boundary-v0.json` 已建立并通过 Schema 校验 | 通过 |
| Gold Set v0 | `tests/fixtures/golden/ws-contract-v0.json` 已建立并通过 Schema 校验 | 通过 |
| `AGENTS.md` 已入库 | 文件存在 | 通过 |
| 数据字段与 DDL 草案对账 | 未发现签字或评审证据 | 阻塞 P1 |
| 首个 Alembic 迁移评审 | `migrations/` 不存在 | 阻塞 P1 |
| 配对/loopback 审计清单 | 有架构规则，无独立审计清单 | 阻塞 P1 |
| 老 MySQL 样本导出 | 未发现可用样本或导出说明 | 阻塞 P1 |

结论：P0 框架前置项已经满足，本任务已完成最小框架切片。下列 P1 行为仍各自受对应 DoR 约束：数据库迁移、配对鉴权、扩展采集与旧数据迁移均不得借本框架任务提前实现。

## 已完成的最小实现切片

1. 根工作区：版本锁定、pnpm workspace、Python 质量工具、Git 忽略规则和统一任务入口。
2. `apps/web`：React 18 + Vite + TypeScript 5 的空壳控制台，仅接健康检查。
3. `apps/extension`：MV3 + TypeScript + Vite 的空壳，不申请 BOSS 权限、不含采集或填充逻辑。
4. `services/api`：FastAPI 模块化单体目录、只读健康接口、结构化错误信封和安全配置校验。
5. `services/worker` 与 `services/worker-renderer`：已建立无业务行为的进程边界；队列实现继续等待 Celery/ARQ ADR 决策。
6. `docker-compose.yml`：API、Web、PostgreSQL/pgvector、Redis、Worker、Renderer；所有宿主端口仅绑定 loopback。
7. `tests/contract` 与 `tests/security`：契约可加载、loopback/config 负向测试及禁止路径扫描。

## 后续人工决策点

- 在 Celery 与 ARQ 之间选择 Worker 基线并记录 ADR；选择前框架不得引入任一队列依赖。
- 确认是否在当前目录初始化 Git；当前目录没有 `.git` 元数据。
- 将本地开发运行时切换到 Node 20、pnpm 9、Python 3.12；当前检测值分别为 Node 24、pnpm 11、Python 3.14。

## 验证证据（2026-09-15）

- JavaScript/TypeScript：Web 4 项、Extension 2 项，共 6 项测试通过；两端类型检查与生产构建通过。
- Python 3.12：12 项测试通过；Ruff、Black、mypy 全部通过。
- Contract：修复基础命令 Schema 漏声明既有 `type` 属性的问题；五份 WS Schema 校验通过，Gold Case 与 Filter 边界夹具通过。
- Container：`jobos-api` 与 `jobos-web` 镜像构建通过；独立 API、WS Gateway、Web 及 Web→API 代理健康探测通过。
- Security：非 loopback、低于 1800ms、并发大于 1 均被配置校验拒绝；实现目录禁止路径扫描为 0 命中。
- License：前端生产依赖均为 MIT；Python 生产依赖元数据为 MIT/BSD-3-Clause 或宽松许可证分类，无商业、GPL/AGPL 或未知依赖进入默认栈。

## 完成条件

- 所有验收测试全绿并附命令输出。
- 依赖许可证扫描无商业、GPL/AGPL 或未知许可证进入默认栈。
- 自评清单说明触碰的目录、契约版本、安全边界、日志数据范围和人工 Review 状态。
- 仅提交待评审改动，不合并、不推送主干。
