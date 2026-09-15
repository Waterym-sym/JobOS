# 13 API 接口设计

> 版本：v1.1（本地配对 token + loopback；新增采集/筛选/候选/投递包/聊天/模板/复盘/KB 导入接口）

## 约定

基础路径 `/api/v1`；JSON 与 UTC ISO-8601；UUIDv7。鉴权：**本地配对 token**（`Authorization: Bearer <local-pairing-token>`）+ loopback 来源校验；WebSocket 握手同样校验 token 与 Origin；无 OAuth/RLS。写请求带 `Idempotency-Key`；版本编辑带 `If-Match`；异步任务返回 `202 + execution_id`。错误 `{code,message,trace_id,details}`，列表 cursor 分页（limit≤100）。

## WebSocket（扩展专用，8788）

`ws://127.0.0.1:8788/ws`。连接第一帧必须是独立握手信封 `{v:1,kind:"handshake",type:"auth_ping"}`，服务端校验后返回 `auth_pong`；成功前不得交换业务消息。业务信封为 `{v:1,kind:"command"|"event",id,type,capture_id|command_id,payload}`。握手、命令/事件全集、`chat.event` 结构、风控暂停语义详见 [21 浏览器扩展集成协议](21-浏览器扩展集成协议.md)。REST 作为 WS 不可用时的回退（批量上报、载荷拉取）。

## 接口总表

### 采集与岗位池

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/captures/batches` | 发起/登记采集批次（人工触发；参数含 delay/detail_limit 下限校验） |
| GET | `/captures/batches/{id}` | 批次进度/统计/风控状态 |
| POST | `/captures/batches/{id}:abort` | 中止（扩展 WS 广播 abort） |
| POST | `/extensions/events` | WS 回退：`job.captured/job.updated/capture.*` 上报 |
| GET | `/pool/jobs` | 岗位池列表（筛选/阶段/来源/关键词） |
| GET | `/pool/jobs/{id}` | 详情（原始层+分析层分离展示） |
| POST | `/pool/jobs/{id}:recover` | 捞回筛选淘汰岗位（记录原因） |
| POST | `/pool/jobs/{id}:refetch-detail` | 请求补采详情（经扩展节流） |

### 筛选与候选

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/PATCH | `/filter-sets[/{id}]` | 条件集版本化 CRUD |
| POST | `/screening-runs` | 运行筛选（body：filter_set_version、范围），202 |
| GET | `/screening-runs/{id}` | 结果：pass/reject + 原因链、按规则统计 |
| POST | `/shortlists` | 确认进候选区（body：job_ids[]） |
| DELETE | `/shortlists/{id}` | 移出候选区 |
| GET | `/shortlists` | 候选区列表（含建议摘要） |

### Job/Match（沿用并扩展）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/jobs:analyze-batch` | 对通过岗位批量 JD 分析 |
| POST | `/jobs/{id}:analyze`、`GET /jobs/{id}/requirements`、`POST /jobs/{id}/revisions/{r}:confirm` | 同 v1.0（去租户语义） |
| POST | `/matches`、`GET /matches/{id}` | 匹配；完成结果含逐项 `state/score/explanation/evidence_ids` 与 `application_advice` |

### 投递包、简历、招呼语

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/applications` | 由候选岗位创建 Application |
| POST | `/applications/{id}/package` | 生成投递包（并行三渠道+招呼语），202 |
| GET | `/applications/{id}/package` | 包详情（版本、Guard、ATS 报告、变体） |
| GET | `/packages/{id}/greetings` | 招呼语变体列表 |
| POST | `/greetings/{id}:select` | 记录被选变体（selected_at） |
| POST | `/resume-versions/{id}:publish` | 发布/导出（含渠道校验） |
| PATCH | `/resume-claims/{id}` | 人工编辑，触发复验 |
| GET | `/resume-versions/{id}/ats-report` | ATS 报告 |
| POST | `/applications/{id}/fill-command` | 向扩展下发 `fill_online_resume`（载荷预检） |
| POST | `/greetings/{id}:copy-command` | 下发 `copy_greeting`（clipboard/draft_input） |
| POST | `/applications/{id}/mark-greeted` | 人工回执已发送（或由确认后的 chat 事件自动生成草稿） |

### 聊天与事件确认

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat-events` | 扩展上报 `chat.event` 草稿（写 chat_message + draft 事件） |
| GET | `/chat-events?status=draft` | 事件确认台 |
| POST | `/chat-events/{id}:confirm` | 确认/修正（body 可覆盖分类）→ 投影 |
| POST | `/chat-events/{id}:reject` | 拒绝草稿（留痕不投影） |
| GET | `/applications/{id}/timeline` | 应用时间线（事件+消息节点） |
| POST | `/applications/{id}/events` | 手工补录事件 |

### 模板子域

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/templates` | 多维检索（channel/type/occupation/lang/color/columns/source/quality + 关键词；维度内 OR、维度间 AND） |
| GET | `/templates/{id}` | 模板详情（元数据+Blueprint 摘要） |
| POST | `/templates/import-docx` | 单个/批量导入（source_dir、pack 选项），202 返回 import_batch |
| GET | `/template-imports/{id}` | 导入进度、成功/失败报告、质量分级 |
| POST | `/templates/{id}/render` | 渲染（body：resume_version 输入、render_params、channel、格式） |
| POST | `/templates/{id}/preview` | 静态多页预览（HTML/缩略图） |
| POST | `/templates` | 另存「我的预设」（user_copy） |
| GET/PUT | `/resume-versions/{id}/editor-state` | A4 编辑器状态（模块顺序/显隐/参数） |
| GET | `/templates/{id}/thumbnail` | 缩略图（本地文件） |
| GET/POST | `/template-packs[/{id}]` | 模板包（内置精选包、自选包） |
| POST | `/resume-versions/{id}:advisor` | Template Advisor 推荐（渠道/职位族/内容量，可拒绝） |

### 复盘与策略

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/applications/{id}/retrospective` | 生成单岗复盘（终态岗位） |
| GET | `/retrospectives[?kind=stage]` | 单岗/阶段汇总列表与详情 |
| POST | `/retrospectives:stage` | 生成阶段汇总（时间窗口） |
| GET | `/strategy-suggestions` | 建议列表（按 scope/status） |
| POST | `/strategy-suggestions/{id}:review` | `approved|rejected` + 理由 |
| POST | `/strategy-suggestions/{id}:mark-applied` | 本人落实后标记 |

### Candidate/KB/工作流

| 方法 | 路径 | 说明 |
|---|---|---|
| PATCH | `/candidates/{id}` | 档案（If-Match） |
| POST | `/artifacts`、`/artifacts/{id}:ingest`、`:complete` | 资产上传/解析（本地签名/直传，无需预签名公网 URL） |
| POST | `/kb/imports/profile-work` | 配置并扫描 `E:\Profile\work` 只读连接器，返回映射预览任务 |
| POST | `/kb/imports/career-kb` | 上传 career-kb JSON 导出并映射 |
| POST | `/kb/imports/resume` | 旧简历导入 |
| POST | `/kb/imports/guided` | 缺口引导录入会话（问答/确认） |
| GET | `/workflow-executions/{id}`、`POST …/:approve` | 进度与审批（shortlist/send 两个节点） |

## 资源契约与错误码

状态码语义同 v1.0（201/202/200/204/400/401/403/404/409/422/429/5xx）。稳定错误码新增：

`PAIRING_TOKEN_INVALID、LOOPBACK_ONLY、EXTENSION_VERSION_MISMATCH、CAPTURE_RISK_HALTED、SCREEN_RULE_INVALID、SHORTLIST_CONFLICT、GREETING_UNSUPPORTED、PAYLOAD_REDLINE、TEMPLATE_DRIFT、TEMPLATE_WRONG_CHANNEL、TEMPLATE_LICENSE_REJECTED、DOCX_IMPORT_FAILED、CHAT_DECODE_DEGRADED、EVENT_ALREADY_CONFIRMED、RETROSPECTIVE_NOT_TERMINAL`；沿用 `VERSION_CONFLICT、RESUME_UNSUPPORTED_CLAIM、WORKFLOW_NOT_APPROVABLE、BUDGET_EXCEEDED`。

错误码 → HTTP / 重试语义映射（以 `contracts/api/openapi.yaml` 为机器真源）：

| code | HTTP | 可重试 | 说明 |
|---|---|---|---|
| PAIRING_TOKEN_INVALID | 401 | 否 | 配对 token 缺失/失效；需重新配对 |
| LOOPBACK_ONLY | 403 | 否 | 非 127.0.0.1 来源或 Origin 不允许 |
| EXTENSION_VERSION_MISMATCH | 400 | 否 | 握手 protocol_version 不兼容，扩展升级 |
| CAPTURE_RISK_HALTED | 409 | 否（须人工恢复） | 风控词/验证码触发批次暂停 |
| SCREEN_RULE_INVALID | 422 | 否 | Filter Set 规则 JSON 不合法 |
| SHORTLIST_CONFLICT | 409 | 否 | 同岗位同批重复确认候选区 |
| GREETING_UNSUPPORTED | 422 | 否 | 招呼语含无证据陈述/禁用表达 |
| PAYLOAD_REDLINE | 422 | 否 | 在线载荷命中红线字段（公司/职位/时间/学历） |
| TEMPLATE_DRIFT | 422 | 否 | 导出回读与 Resume JSON 不一致 |
| TEMPLATE_WRONG_CHANNEL | 422 | 否 | showcase 模板进入 ATS 导出队列 |
| TEMPLATE_LICENSE_REJECTED | 422 | 否 | 模板 license 缺失或禁止入库用途 |
| DOCX_IMPORT_FAILED | 422（逐条记录，批次 202） | 否（看失败报告修复后重导） | 损坏/加密/版式无法识别/槽位全 unknown |
| CHAT_DECODE_DEGRADED | 不作为错误；事件带 `decode_source=dom` 与下调置信度 | — | 网络层解码失败降级 DOM，等待人工确认 |
| EVENT_ALREADY_CONFIRMED | 409 | 否 | 草稿已 confirmed/rejected |
| RETROSPECTIVE_NOT_TERMINAL | 422 | 否 | 岗位未到终态不允许生成单岗复盘 |
| VERSION_CONFLICT | 409 | 否 | If-Match/乐观锁冲突 |
| RESUME_UNSUPPORTED_CLAIM | 422 | 否 | Claim 无有效证据，Guard 阻断 |
| WORKFLOW_NOT_APPROVABLE | 409 | 否 | 节点不在 waiting_approval 或审批前置未满足 |
| BUDGET_EXCEEDED | 429 | 可（降载/换 provider） | 任务 token/成本预算超限 |

5xx 仅用于未预期故障，携带 `trace_id`；可重试错误客户端用指数退避，风控类错误禁止自动重试。

Evidence/聊天原文不嵌入列表响应；明细按资源单独取且记录审计。所有响应 DTO 向后兼容加字段；OpenAPI 为真源，CI 做 schema 兼容 diff 与 WS 协议契约测试。

## 审批接口

`:approve`（节点 shortlist_approval/send_approval）：`decision=approve|reject|return、expected_node_version、reason`；原子校验 waiting_approval；重复提交返回原决定；审批连同 snapshot hash 入审计。send_approval 通过后系统只下发填充/复制命令，**不产生任何发送动作**。
