# contracts/ — 机器可读契约

> 状态：WS 与 REST 核心契约标为 `v1`；其路径/形状已随 P1 切片扩展。数据库 skeleton、Workflow DSL 与 Filter Set 仍是阶段性草案；可执行 DDL 只在 Alembic。当前实现及人审状态见[项目状态快照](../docs/delivery/06-项目状态快照.md)。

## 真源规则

1. **语义真源是文档**（`docs/architecture/`，尤以 21/13/12/15/08 篇为准），本目录是**形状真源**。两者冲突：先评审改文档，再改契约，禁止反向。
2. 契约只允许**向后兼容加字段**；破坏性变更需新协议版本 + ADR 评审。
3. `packages/contracts-py`（Pydantic）与 `packages/contracts-ts`（TS 类型）由本目录**单向生成**，禁止手改。
4. 变更必须同时更新对应文档、契约测试与示例；CI 执行：JSON Schema 双端一致性、OpenAPI 兼容 diff、WS 协议契约测试。

## 文件索引

| 文件 | 内容 | 语义真源 |
|---|---|---|
| `ws/protocol.schema.json` | WS 信封（command/event）、回执四态 | 21 篇 §2–4 |
| `ws/handshake.schema.json` | 扩展发起 auth_ping、服务端返回 auth_pong | 21 篇 §2 |
| `ws/commands.schema.json` | 6 个服务端→扩展业务命令（无 send 类） | 21 篇 §3 |
| `ws/events.schema.json` | 7 个扩展→服务端事件 | 21 篇 §4 |
| `ws/raw-job.schema.json` | 列表/详情两档岗位数据契约 | 21 篇 §5 |
| `ws/chat-event.schema.json` | 聊天回采消息与草稿分类 | 21 篇 §6 |
| `api/openapi.yaml` | REST v1 核心路径；同时包含已实现与后续阶段规划路径，不能仅凭出现于契约判断已上线 | 13 篇 |
| `db/0001_baseline.skeleton.sql` | PG16 比对草案，非可执行迁移；实际 revision 见 `migrations/versions/` | 12 篇 |
| `dsl/workflow.schema.json` | Workflow DSL 与静态门禁 | 15 篇 |
| `filters/filter-set.schema.json` | Stage-0 筛选规则 rule_json（八组） | 8 篇 |

## 协议版本协商

- WS 信封固定 `v:1`；连接第一帧由扩展提交独立 `handshake.auth_ping`，成功后服务端返回 `handshake.auth_pong`；协议不匹配返回 `EXTENSION_VERSION_MISMATCH`。
- 收到未知 `type`：不得崩溃，须按「未知命令拒绝并回执 error / 未知事件忽略并记录指标」处理。
- **协议中不存在且永不注册**：`send_message`、`deliver`、`auto_apply`、`auto_greet`、`auto_next_page:true`、自动上传（ADR-009，21/24 篇）。
