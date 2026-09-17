# P1-007 多用户架构与界面融合评审门

```yaml
task: P1-007-multiuser-architecture-gate
status: in_progress
domain_owner: Architecture / Security / Product
architecture_refs:
  - ARCH-SEC-001
  - ARCH-SEC-003
  - ARCH-DATA-001
  - ARCH-API-001
  - ARCH-CONTRACT-001
  - ARCH-EXT-001
  - ARCH-TPL-001
contracts:
  - contracts/api/openapi.yaml
  - contracts/db/0001_baseline.skeleton.sql
  - contracts/db/0005_multiuser.skeleton.sql
  - contracts/ws/protocol.schema.json
adr:
  - docs/architecture/decisions/ADR-013-多用户与公网入口.md
data_classification: restricted
human_approval: required
nfr:
  - 跨账号访问与越权写入零成功
  - 扩展 WS、数据库、Worker 不直接公网暴露
  - 聊天原文不上传公网服务或第三方
acceptance_tests:
  - 独立评审确认用户角色、owner 传播、旧数据归属、回滚前置条件与公网边界
  - 检查全部现有数据访问路径、缓存和后台任务的归属清单
  - 检查来源 UI 复制授权及示例个人信息/模拟行为剔除清单
red_lines:
  - AGENTS.md 禁止项 1–10（仅单用户目标与本文件修改限制按本人裁决调整）
  - 不弱化原 P0–P6 阈值、Gold Set、自动外发与聊天隐私测试
```

## DoR 与本人裁决

- 2026-09-18 已确认：公网多用户目标、本期不实际部署；邮箱密码、邀请注册、服务器引导首个管理员、管理员单次密码重置；求职者与招聘者双角色，招聘者仅空工作台；旧数据归首个管理员。
- 已确认来源仓库界面复制授权；保留视觉、改 JobOS 文案；完整入门流程使用真实 PDF/DOCX 私有上传与空白资料，不复制模拟登录、上传、注销或示例个人资料。
- 求职者登录后的左侧流程导航顺序、标签、结构与样式不变。本机扩展/聊天链路与公网用户分离。
- 已检索索引 `ARCH-SEC-001`、`ARCH-DATA-001`、`ARCH-API-001`、`ARCH-CONTRACT-001`、`ARCH-EXT-001`；新增 `ARCH-SEC-003` 和 ADR-013 处理原单用户范围之外的决策。
- 2026-09-18：本人在任务对话中报告 ADR-013 与本任务的独立评审结论均为“通过”；据此解除编码前评审门。未提供独立评审单文件，实施后的代码与安全验收仍需单独留证。

## 人审后实施顺序

1. 契约：身份、会话、邀请/重置、用户资料、简历文件、owner 约束及错误码。
2. Alembic：旧数据归属、共享目录与用户数据区分、可逆迁移及不兼容降级拒绝。
3. 认证/授权：服务端会话、CSRF/Origin、角色与归属、限流、审计；移除浏览器共享配对令牌路径。
4. UI：来源登录/账号设置/完整入门视觉移植与真实行为；保持现有求职者侧栏不变。
5. 隔离、迁移、删除、视觉与安全负例；再由人审决定是否可合并。本任务不包含公网部署。

## 当前实现的归属审查清单

| 位置 | 当前事实 | 人审需定下的边界 |
|---|---|---|
| `capture_source` | `code` 为全局唯一的招聘平台目录 | 保持共享、不可承载用户秘密 |
| `batch_run`、`raw_job`、`raw_company`、`shortlist`、`screening_entry`、`ws_event_inbox` | 现有迁移均无 owner；岗位与公司唯一键为全局 `source_id + ext_id` | 用户归属、复合唯一键、旧数据归属与跨账号查询/写入 |
| `capture_repo.py` | SQL 直接按对象 ID 或全局列表查询；`_DUP_COUNTS` 以批次 ID 缓存 | 逐条加入服务端归属过滤与负例，缓存键/生命周期对账 |
| `enrich.py`、`registry.py` | 补全队列及扩展实例注册为进程级单例 | 本机扩展只服务本机链路；公网模式关闭，不让远程账号共享队列或实例 |
| `apps/web/server.mjs` | 每个浏览器 API 请求由 Web 代理注入同一配对令牌 | 改为用户会话代理；配对令牌仅留本机扩展端，浏览器不可读取 |
| `pages_auth.tsx`、来源 `useAuth.ts` | 分别是本地 PIN 和 `localStorage` 模拟登录 | 两者均不得继续担当身份真源；会话及角色必须由服务端给出 |

本表仅覆盖当前已实现的持久表/进程态；实现前须由 schema 与 SQL 搜索生成完整清单，新增表也必须分类为共享或用户私有。

## 实施进度（2026-09-18，仍未完成）

- 本人进一步要求取消邀请码与命令行管理员初始化，改为网页邮箱密码自助注册。该要求与已接受的 ADR-013 身份决策冲突；已提出 ADR-014 待独立评审。**评审前保留现有认证实现，不通过 UI 假装开放注册。**

- 已先更新 API/DB 对比契约；新增账号、会话、邀请、重置、资料、简历文件表与 owner 列。旧数据仅由服务器命令显式归属首个管理员，不在迁移时猜测归属。
- 0005 在隔离库验证 upgrade/downgrade；多账号 downgrade 明确拒绝。尚未在用户库运行，也未部署公网。
- 已接入服务端邮箱密码登录、邀请、管理员重置、Cookie+CSRF、资料与私有文件上传；Web 代理默认仅允许管理员会话使用旧版 API，公网模式拒绝旧版 API，后端 `PUBLIC_MODE` 仍被强制关闭。
- 来源登录/账号设置/入门 CSS 已移植，替换模拟认证与预填资料；求职者左侧流程顺序/标签/结构保持。普通求职者的旧岗位流程暂时显式锁定，避免共享旧数据；招聘者进入独立空工作台。
- Web 类型检查、58 项测试与构建通过；隔离库账号集成测试此前通过。**尚欠**旧流程全链路 owner 查询/写入与缓存/后台任务隔离、完整跨账号 ID 负例、视觉截图比对及独立代码安全评审。当前状态不得称为公网可发布，也不得合并。
