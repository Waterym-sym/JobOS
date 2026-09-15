# 15 Workflow DSL 设计

> 版本：v1.1（换新主流程示例；静态门禁：禁外部发送 handler、greeting 前置证据、render 声明渠道、聊天走事件入口）

> 机器契约：DSL JSON Schema 草案见 [`../../contracts/dsl/workflow.schema.json`](../../contracts/dsl/workflow.schema.json)（v0-draft，P2 前冻结），含禁止 handler 名的静态门禁注释。

## 设计约束

DSL 是受限、可版本化的 YAML/JSON 声明，不是可执行代码。`handler` 必须在服务端注册表中且标注 `side_effect_level`；表达式只支持白名单字段比较、布尔/数值逻辑；无函数调用、无文件/网络访问、无 eval。JSONPath 子集做 mapping。

```yaml
id: boss_application
version: 1.0.0
input_schema: BossApplicationInput@1
default_timeout_seconds: 1800
max_concurrency: 4
data_classification: local
budget: {max_tokens: 120000}
nodes:
  - {key: screen_filter, type: task, handler: screening.run_rules}
  - {key: parse_jd, type: task, handler: job.parse_batch, depends_on: [screen_filter],
     parallel: {items_path: "jobs.passed", max_fanout: 4}, join: allow_partial}
  - {key: evidence, type: task, handler: evidence.retrieve_and_judge, depends_on: [parse_jd]}
  - {key: match, type: task, handler: matching.calculate_with_advice, depends_on: [evidence]}
  - {key: shortlist, type: human_approval, approver_policy: owner, timeout_hours: 72,
     depends_on: [match]}
  - {key: plan_resume, type: task, handler: resume.plan, depends_on: [shortlist]}
  - {key: render_ats, type: task, handler: template.render,
     params: {channel: ats}, depends_on: [plan_resume]}
  - {key: render_showcase, type: task, handler: template.render,
     params: {channel: showcase, template_from: selection}, depends_on: [plan_resume]}
  - {key: online_payload, type: task, handler: resume.build_online_payload, depends_on: [plan_resume]}
  - {key: greetings, type: task, handler: greeting.generate_ab,
     params: {variants: 3}, depends_on: [plan_resume, evidence, match]}
  - {key: guard, type: task, handler: guard.verify_package,
     depends_on: [render_ats, render_showcase, online_payload, greetings], join: all_success}
  - {key: send_approval, type: human_approval, approver_policy: owner, timeout_hours: 72,
     depends_on: [guard]}
```

回采/复盘是独立事件驱动流程 `retrospective@1.0`：入口节点 `event_wait` 订阅 `chat.event_received`（仅消费 `review_status=confirmed`），终态条件触发 `retrospective.run → strategy.propose`，strategy 节点输出只写建议表，无任何配置写回 handler。

## Schema 与静态校验（v1.1 门禁）

顶层：`id/version/input_schema/nodes`，可选 `metadata/default_timeout_seconds/max_concurrency/data_classification/budget`。节点需 `key/type`；`depends_on` 构成 DAG；task 需存在的 handler；approval 必须超时；parallel 需 `items_path/max_fanout`。

**v1.1 强制静态门禁**（校验不通过则整个定义不可发布）：

1. **无外部副作用 handler**：注册表 `side_effect_level` 仅允许 `local_read|local_write|extension_command`；启动期扫描，名称/元数据匹配 `send|deliver|apply_external|next_page|upload` 的 handler 一律拒绝注册。DSL 中可达路径不得出现扩展 `fill_online_resume/copy_greeting` 之外的 extension_command，且这两个只能在 send_approval 之后由 API 单次下发，不编入自动执行图。
2. **greeting 前置**：`greeting.*` 节点必须依赖 evidence 与 match 节点输出（防止无证据话术）。
3. **render 声明渠道**：`template.render` 必须显式 `params.channel ∈ {ats,showcase}`；使用 showcase 模板渲染 ats 渠道报 schema 错。
4. **Guard 必经**：任何产出可投递版本的路径必须经过 `guard.verify_package`（all_success）。
5. **聊天只进事件入口**：chat 数据只能由 `event_wait` 消费已确认事件；禁止 task 节点直接拉取 chat_message 原文到第三方模型节点（数据分级检查）。
6. 敏感数据流向：restricted 级（聊天/联系方式）不得流向 `model_route=third_party` 的节点。
7. 最大 fanout/重试/超时/成本在本机上限内；审批必须有超时；错误定位到节点与字段，定义不可部分发布。

定义不可原地修改，使用语义版本；执行绑定版本与输入快照（含模板版本、renderer 版本）。

## DSL 字段补充

task：`input_mapping、output_key、timeout_seconds、retry、on_failure、idempotency_key、params、side_effect_level(继承)、data_policy`。condition 只接受声明变量。approval：`approver_policy(固定 owner)、message_template、timeout_action(cancel)`。event_wait（v1.1 新增）：`event_name、filter、timeout_policy`。

## 运行语义

`when=false` 记 `skipped`；依赖 skipped 由 join 决定。投递包并行组 `all_success`：任一渲染/Greeting 被 Guard 阻断，整包不发布。节点超时先撤销外部请求再标 `timed_out`；`on_failure ∈ fail|retry|continue_with_default|goto`，goto 过循环检测。采集相关 task 额外响应 `abort` 信号与 `capture.error{risk}` 暂停。子工作流传最小输入、继承 trace，不继承额外权限。

## 示例质量门禁

- 任何产出投递版本/招呼语的 DSL，前置路径必须有 Truth Guard 成功节点与对应人工审批；
- 任何向第三方 Provider 发送 restricted（聊天）数据的定义被策略拒绝；
- 任何包含自动发送/投递/翻页语义的定义无法通过注册与发布（单元测试对 DSL 样例库做红队断言）。
