# 14 AI 模型与 Prompt 设计

> 版本：v1.1（新增 Screen/Greeting/Retrospective/Template Advisor 四类 Agent；聊天上下文本机边界）

## 分层模型策略

| 任务 | 首选方式 | 约束 |
|---|---|---|
| Stage-0 筛选、薪资/日期/年限/活跃度解析 | **纯规则/解析器** | 不调 LLM；AI 打分仅可选附加 |
| JD/事实提取 | LLM 结构化输出 | JSON Schema、低温度、置信度 |
| 检索 | BM25 + embedding + rerank | 先 PII/项目性质过滤，后模型 |
| Evidence Judge | 受限 LLM | 只判给定文本，不补事实 |
| 简历/招呼语 | LLM | 输入限 approved facts/evidence 与岗位字段槽位 |
| 模板推荐 | 规则优先，LLM 可选 | 只读模板元数据与 Resume JSON 结构 |
| ATS 检查 | 确定性解析器 | LLM 仅解释问题 |
| 复盘 | LLM（本机/脱敏侧优先） | 可访问全链路+聊天原文；无写事实权限 |

## Prompt Registry

每条模板版本化：`prompt_id、version、system_policy、input_schema、output_schema、model_route、temperature、max_tokens、evaluation_set、data_policy`。每次调用写 `model_run`：输入哈希、上下文引用（聊天原文只允许传引用/脱敏文本）、输出、token、成本、延迟、trace id。

不可信 JD、文件、网页、聊天内容只作数据注入明确分隔符。工具 allowlist：`get_candidate_fact、retrieve_evidence、get_job_requirement、get_template_meta`；无 SQL/Shell/任意网络；复盘 Agent 额外只读 `get_application_bundle`（含脱敏聊天）。Schema 失败一次修复重试，仍失败转人工。

模型走**用户自有 Key（仅本机配置）或本地模型**；`data_policy` 标注每类 Prompt 是否允许第三方：默认 JD/简历类可用第三方（不含 restricted PII），**聊天复盘默认仅本地模型/脱敏摘要**，开关显式启用并二次确认。预算按执行/节点两级。

## Agent 与工具权限矩阵（v1.1）

| Agent | 最小上下文 | 工具 | 明确禁止 |
|---|---|---|---|
| JD Analyst | 单个 Raw Job/JD、ontology | extract/normalize | Candidate PII、最终匹配分、聊天原文 |
| Screen Analyst | 结构化岗位字段（可选 AI 附加分） | read_fields | 修改规则、自动淘汰、访问 JD 以外页面 |
| Evidence Analyst | Requirement、授权 chunks | retrieve/judge | 改事实、访问全库 |
| Resume Writer | Plan、approved facts | fact lookup | 新建能力、读原件全集 |
| Greeting Writer | 岗位字段槽位、strong_evidence 引用、facts 摘要 | fact lookup | 注入聊天历史、虚构公司信息、承诺类表达 |
| ATS Analyst | 导出解析、JD 词表 | diagnostics | 改写/发布 |
| Template Advisor | 模板元数据、Resume JSON 结构统计（模块数/篇幅/渠道） | get_template_meta | 读简历原文 PII、自动替用户选定模板 |
| Retrospective Analyst | 单岗全链路引用 + 聊天原文（本机/脱敏） | get_application_bundle | 写事实/证据库、自动调权、任何外发动作 |

工具调用入参/出参/授权进 trace；模型索要更多数据不扩权；「忽略以上指令」记潜在注入告警。

## 新增 Prompt 模板要点

1. **screen_explain@1**（可选）：输入规则命中结构，输出人话解释；不允许改变 verdict。
2. **greeting_ab@1**：输出 3 条变体 JSON；system policy 内置变量槽白名单、证据引用要求、禁用承诺/虚构了解/绝对化；输出自检 `factual_spans[].evidence_id`，无证据的事实性 span 由 Guard 阻断。
3. **chat_classify@1**（扩展/服务端辅助）：把解码消息分为 chat_read/chat_replied/chat_rejected/interview_scheduled/interview_rejected/offered/other + 置信度；只产草稿。
4. **retrospective@1**：输入去标识化的 JD 摘要、匹配依据、简历版本/模板参数、招呼语变体与选择、聊天时间线与脱敏原文；输出「事实经过（引用消息 ID，不复制敏感原文）、效果归因（变体/模板/侧重）、单条/多条可执行建议（scope 分类）」；建议必须可追溯到具体记录，不允许泛泛鸡汤。

## 评估集（与 16 篇对齐）

- 筛选规则边界集（薪资口径、否定语境、活跃度、同 HR/已沟通去重）；
- 招呼语：溯源合格率（事实 span 有证据）、禁用表达 0 泄漏、变量槽渲染正确率、长度合规率；
- 聊天分类：约面/拒绝/普通回复准确率（结构化 interview 消息为重点样本）；
- 复盘：建议可追溯率、scope 分类准确率、敏感原文外泄检测（红队）；
- 模板 Advisor：渠道推荐正确率（ATS 岗不推 showcase）、拒绝推荐不阻塞流程。
Prompt 改动须先过 Gold Set 与注入/脱敏红队集，再在本机启用。

## 质量、成本与回退

规则/小模型优先，top-K Judge、规划、写作、复盘走强模型或本地大模型；缓存键 `input_hash + prompt_version + model_route`。供应商超时有限重试；换模型若影响事实语义必须人工复核。复盘与聊天相关任务在 Provider 不可用时不降级到「明文外发」，而是等待或仅本机规则摘要。

## 负责任 AI

沿用 NIST AI RMF（Govern/Map/Measure/Manage）：模型卡、用途边界、风险登记、评估集、事故处理。受保护属性与代理变量（婚育、民族、照片、活跃度推测的个人品行等）不进排序特征；Outcome 学习仅做观测与人工审核的建议（ADR-003/008）。
