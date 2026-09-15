# P1-002 本地配对与 WS Gateway

```yaml
task: P1-002-pairing-ws-gateway
status: ready_for_human_review
domain_owner: Platform
architecture_refs:
  - ARCH-API-002
  - ARCH-EXT-001
  - ARCH-REL-001
  - ARCH-SEC-001
  - ARCH-CONTRACT-001
  - ARCH-AIAGENT-001
contracts:
  - contracts/ws/protocol.schema.json
  - contracts/ws/handshake.schema.json
  - contracts/ws/commands.schema.json
  - contracts/ws/events.schema.json
data_classification: confidential
human_approval: required
nfr:
  - 非 loopback 宿主入口 100% 拒绝
  - 错误配对凭据 100% 拒绝
  - 配对凭据不进入仓库、镜像、URL 或日志
acceptance_tests:
  - 正确凭据与协议版本完成一次握手
  - 错误或缺失凭据返回稳定错误码并关闭连接
  - 不允许的 Origin 被拒绝
  - 不兼容协议版本返回稳定错误码且不重试
  - 未鉴权连接不能提交任何业务事件
  - 未知消息类型不会导致 Gateway 崩溃
red_lines:
  - AGENTS.md 禁止项 1、2、4、5、8、9
  - 不实现采集、填充、聊天解码或任何对外动作
```

## 契约冲突记录（已裁决）

1. 专题 21 §2 的时序规定由扩展向服务端提交 `auth_ping`，服务端返回 `auth_pong`。
2. 专题 21 §3 与 `contracts/ws/commands.schema.json` 将 `auth_ping` 放在“服务端 → 扩展”命令全集。
3. `contracts/ws/events.schema.json` 没有客户端握手事件，冻结契约中也没有 `auth_pong` 的形状。
4. `events.schema.json/$defs/baseEvent` 要求 `type`，但未在 `properties` 声明；由于 `additionalProperties:false`，合法事件无法通过组合 Schema。
5. 专题 17 要求 PostgreSQL 与 Redis 仅在容器网络使用、不暴露宿主；当前 `docker-compose.yml` 尚有两项 loopback 端口映射。

依据 `ARCH-CONTRACT-001`，第 1–3 项涉及消息方向和契约形状，已于 2026-09-15 取得 Owner 明确批准，并按“文档 → 契约 → 双端实现 → 契约测试”处理。

## 推荐裁决

采用客户端发起的握手：

- 扩展连接 `ws://127.0.0.1:8788/ws` 后，第一帧提交 `auth_ping` 请求。
- Gateway 校验宿主入口、Origin、配对凭据和 `protocol_version`。
- Gateway 返回 `auth_pong{supported, min_version}`；失败使用统一错误信封后关闭连接。
- `auth_ping/auth_pong` 独立为 handshake 消息，不计入七个业务命令或七个业务事件。
- 未通过握手的连接不得提交业务事件或接收业务命令。

选择该方案后需要同步修订专题 21 §3、WS Schema 与 Gold Case，再实现服务端和扩展客户端。

## 不推荐方案

由服务端先发送 `auth_ping`、扩展再回应。该方向与专题 21 的现有配对时序、凭据由扩展持有并主动提交的设计不一致，会增加挑战状态与超时处理，当前没有相应语义依据。

## DoR 与裁决结果（2026-09-15）

| 检查项 | 证据 | 结论 |
|---|---|---|
| architecture_refs 已检索 | ARCH-API-002、ARCH-EXT-001、ARCH-REL-001、ARCH-SEC-001、ARCH-CONTRACT-001、ARCH-AIAGENT-001 | 通过 |
| 握手方向与消息分类 | Owner 批准独立 `kind: handshake`、扩展首帧发起方案 | 通过 |
| 契约先行 | 专题 13/21、索引库与 WS Schema 先于双端实现修订 | 通过 |
| 配对/loopback 审计清单 | 本任务头 NFR、验收测试和安全测试形成独立清单 | 通过 |
| 数据库迁移前置 | 本任务不涉及 DDL、迁移或数据字段 | 不适用 |
| 人工 Review | 实现与证据已就绪，未合并、未推送 | 待人工 Review |

## 已完成实现

1. 新增独立 `handshake.schema.json`，冻结客户端 `auth_ping` 与服务端 `auth_pong`；同步修复事件基础 Schema 的既有 `type` 属性组合缺陷。
2. Gateway 仅接受 loopback（容器桥接场景只在显式 container mode 放行私网对端）与合法 Chrome Extension Origin；错误凭据、错误首帧和版本不兼容均返回稳定结果后关闭。
3. 配对令牌可由环境注入，或首次运行时安全生成到忽略入库的本机文件；比较使用恒定时间函数，日志只记录事件、结果、trace 与版本元数据。
4. MV3 扩展增加 Options 配对页；端点固定为 `ws://127.0.0.1:8788/ws`，令牌只存 `chrome.storage.local`，配置变更时单次重连，无循环重试。
5. 扩展仍无 `host_permissions`、`content_scripts` 或网页访问能力；Gateway 握手后对尚未实现的消息只做无载荷元数据审计，不注册业务 handler。
6. Compose 删除 PostgreSQL 与 Redis 的宿主端口，仅 API、Gateway、Web 显式绑定 `127.0.0.1`。

## 验证证据（2026-09-15）

- JavaScript/TypeScript：Extension 6 项、Web 4 项，共 10 项测试通过；两端类型检查与生产构建通过；Extension 另在锁定的 Node 20.18.3 / pnpm 9.15.5 隔离容器复验通过。
- Python 3.12：19 项测试通过；Ruff、Black、mypy 全部通过。覆盖令牌文件 `0600`、正确/错误令牌、协议不兼容、Origin/peer、未鉴权业务帧、UUIDv7 与日志不泄露。
- Contract：WS Schema 与 Gold Case 全部通过；握手使用独立 Schema，业务命令仍为 6 个、业务事件仍为 7 个。
- Container：`jobos-api`、`jobos-web` 镜像重建通过；新 API 镜像健康检查返回 `ok`，真实 WebSocket 烟测完成 `auth_ping → auth_pong`。
- Network：Compose 渲染结果中 PostgreSQL/Redis `ports=null`；API 8000/8788 均为 `host_ip=127.0.0.1`。
- Security：排除构建产物后的实现目录禁止动作关键字与密钥模式扫描为 0 命中；仅保留 `chat_to_third_party=false` 防护配置。

## 自评与人工 Review 边界

- 触碰目录：`contracts/ws`、专题 13/21 与架构索引、`services/api`、`apps/extension`、配置、Compose、契约/安全测试。
- 数据范围：握手仅处理配对令牌、扩展版本与协议版本；不处理职位、简历或聊天数据。令牌不进入 URL、日志、构建产物或仓库默认配置。
- 红线证明：未增加任何采集、翻页、填充、上传、沟通或发送路径；无业务命令可在握手前执行。
- 需人工 Review：独立 handshake 契约、Origin/容器桥接边界、令牌本机存储、Compose 网络变更均属于 🟡 项；当前只提交待评审状态，不合并、不推主干。
