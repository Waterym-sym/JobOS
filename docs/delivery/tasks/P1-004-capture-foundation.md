# P1-004 Capture 领域基础闭环

```yaml
task: P1-004-capture-foundation
status: ready_for_human_review
domain_owner: Capture
architecture_refs:
  - ARCH-DATA-001
  - ARCH-CONTRACT-001
  - ARCH-API-001
  - ARCH-API-002
  - ARCH-EXT-001
  - ARCH-SEC-001
  - ARCH-OBS-001
  - ADR-005
  - ADR-009
contracts:
  - contracts/api/openapi.yaml
  - contracts/db/0001_baseline.skeleton.sql
  - contracts/ws/protocol.schema.json
  - contracts/ws/commands.schema.json
  - contracts/ws/events.schema.json
  - contracts/ws/raw-job.schema.json
data_classification: internal
human_approval: required
nfr:
  - REST 仅 loopback 且必须使用配对 Bearer token
  - API 与数据库实体 ID 使用 UUIDv7
  - source+ext_id 与 WS event id 双重幂等
  - 采集间隔不低于 1800ms、保留抖动、并发恒为 1
acceptance_tests:
  - Alembic 是唯一数据库迁移入口
  - 未鉴权 REST 请求与非 loopback 请求均被统一错误信封拒绝
  - 浏览器端无法读取配对 token，Web 代理只在服务端注入
  - 列表档与详情档按 source+ext_id 合并且原始 JSON 分别保留
  - 重复 WS event id 不产生第二次领域写入
  - capture.error risk=true 只进入 risk_halted 且不重试
red_lines:
  - AGENTS.md 禁止项 1、2、4、5、8、10
  - 协议中不存在发送、投递、自动翻页或自动上传命令
  - 不采集或处理聊天原文
  - 不降低 Origin、loopback、配对 token 校验
```

## 目标

冻结 Capture 域首个可执行数据库迁移，并建立控制台人工触发采集、WS 事件入库、批次状态和岗位只读列表的最小闭环。外部动作仍由本人完成；本任务不实现填充、聊天、发送、投递、自动翻页或上传。

## DoR 审计（2026-09-16）

| 检查项 | 证据 | 结论 |
|---|---|---|
| 架构检索 | 已核对上述 ARCH/ADR 与 12、20、21、23、24 篇 | 通过 |
| 机器契约 | API、WS、DB 草案已逐项对账；先更新契约再实现 | 通过 |
| 数据 owner/PII | `capture_source/batch_run/raw_job/ws_event_inbox` 归 Capture；不含聊天 PII | 通过 |
| 迁移策略 | 仅 Alembic 前滚迁移；删除自制 SQL runner | 通过 |
| 安全策略 | REST 使用 loopback + Bearer；Web 代理服务端注入，浏览器不可见 | 通过 |
| 人工 Review | DDL、契约、默认配置与扩展命令均为 🟡 | 必须 |

## 范围

1. 首个 Alembic Capture migration 与迁移 smoke test。
2. `/api/v1` Capture REST 契约、鉴权和统一错误信封。
3. 六命令白名单中的 `capture_list/capture_details/abort` 人工触发路径。
4. WS 事件校验、事件 ID 幂等、`source+ext_id` 合并及风险暂停。
5. 控制台只读状态与人工采集表单；配对令牌不下发浏览器。

## 非范围

- 聊天采集、在线填充、招呼语、发送/投递、自动翻页、上传。
- Screening、Shortlist、Resume、Retrospective 等其他领域。
- 自动重试、自动调权、策略自动应用。

## Review 关注点

- 首个 Alembic revision、表/索引/幂等收件箱是否符合 Capture owner 边界。
- REST 配对令牌由 Web 本机代理注入的部署方式。
- `capture.error{risk:true}` 的终态与无重试证明。

## 验证证据（2026-09-16）

- Python 3.12：46 项默认测试通过，1 项 PostgreSQL 集成测试按默认配置显式跳过。
- PostgreSQL 16：在无持久卷的隔离实例中执行 `alembic upgrade head` 成功；Capture DB 集成测试通过。
- 数据：验证列表/详情按 `source+ext_id` 合并、两档原始 JSON 独立保留、重复计数、实体 UUIDv7、WS event id 幂等。
- 安全：缺失 token 返回 401、非 loopback 返回 403、令牌回显路由为 404、违禁命令注册失败；错误均为统一信封。
- 静态质量：ruff 通过；mypy strict 对 19 个 Python 源文件通过；Alembic 离线 SQL 生成通过。
- Web：12 项测试、TypeScript 检查与生产构建通过；代理服务端注入 token，浏览器 token 获取器扫描为 0。
- Container：API 与 Web 最终镜像基于 Python 3.12 / Node 20.18.3 成功重建；Compose 配置校验通过。

## 自评清单

1. 没有发送、投递、自动翻页、自动上传或聊天处理路径。
2. `capture_list` 固定携带 `auto_next_page:false`；节流 DTO 下限 1800ms；配置并发恒 1。
3. `capture.error{risk:true}` 只写 `risk_halted`，没有自动重试。
4. REST 全部位于 `/api/v1`，健康检查之外强制 loopback + Bearer token。
5. 配对 token 只在 API/WS 与本机 Web 代理之间流转，不进入浏览器响应、日志或构建产物。
6. Alembic 是唯一迁移入口；API 启动不会自动执行 DDL。
7. 新行为均有行为测试或红线负向测试；任务保持待人工 Review，未提交、未合并、未推送。
