# 10 Resume Engine 技术方案

> 版本：v1.1（同一 Claim 集合三渠道渲染；新增在线载荷与 Greeting Generator；模板机制引用专题 22）

## 管线

```text
Resume Planner → Claim Generator → Truth Guard
  → ① ATS 渲染（template.render, channel=ats → PDF/DOCX/MD）
  → ② Showcase 渲染（template.render, channel=showcase → PDF/PNG/HTML）
  → ③ OnlineResumePayload（四模块纯文本）
  → Greeting Generator（A/B 多变体）
  → Guard.verify_package → ATS 检查 → 人工选择/发布/发送
```

模型只生成结构化 JSON，不直接生成富文本。三渠道 + 招呼语**共享同一份 Claim 集合与证据链**；模板相关机制（正交模型、Blueprint、DOCX 导入、渲染器、编辑器、Advisor）全部见 [22 简历模板与渲染引擎](22-简历模板与渲染引擎技术方案.md)，本篇只定义 Claim→槽位映射契约与在线载荷。

| 组件 | 输入 | 输出 |
|---|---|---|
| Planner | Job、Match、投递建议 | section 优先级、项目排序、关键词/篇幅预算、渠道计划 |
| Generator | Plan、approved facts/evidence | Resume Claim 列表（带 evidence_ids） |
| Guard | Claim、Greeting、Evidence | support/risk 状态（见 11） |
| Payload Builder | Resume JSON | 四模块在线载荷 |
| Greeting Generator | 岗位字段槽位 + approved facts | GreetingVariant[]（默认 3 条） |
| Renderer（专题 22） | Resume JSON + 模板参数 | PDF/PNG/HTML/DOCX/MD |
| Versioning | 确认后的包 | 不可变 Resume Version + Package |

## Resume Claim 契约

```json
{"section":"project","text":"基于 Python 构建知识库检索服务，人工检索耗时降低 40%","entities":["Python"],"metrics":[{"value":40,"unit":"%"}],"evidence_ids":["ev_123"],"support_status":"supported","risk_level":"low"}
```

Claim 必带来源；人工编辑使其进入 `needs_revalidation`。已使用（发布/已发送）版本要求全部 Claim `supported`，只能派生不能改。**模板不得承载业务事实**：槽位只引用 Resume JSON 路径，渲染后 Claim 文本集合必须与输入快照一致（Guard + 回读双校验）。

生成策略是真实重组：按 JD 强调有证据的职责与结果，弱化无关内容；不把「类似框架经验」写成「熟练指定框架」；`learning_ref` 项目不进工作经历 Claim；`secondary_dev` 必须带许可/二开表述。

## Resume Plan Schema

`target_role、channel_plan、language、template_candidates(ats/showcase)、section_order、selected_experience_ids、selected_project_ids(含 nature)、requirement_coverage_map、keyword_budget、length_budget、greeting_brief、omitted_reason`。每个选入项说明覆盖的 Requirement；未覆盖 must-have 以 Gap 保留，不得靠删需求让分数变好。`channel_plan` 结合 `ats_direct_post` 投递建议给出（直投岗：在线载荷+ATS 附件双备）。

## Claim → 槽位映射契约（与 22 篇的边界）

1. Resume JSON 是唯一事实源，结构按 Content Module（M01–M25）组织；模块/字段级显隐与排序由 Plan + 模板参数决定。
2. Blueprint 的 `slot_map` 只能指向已存在路径；渲染时未知槽位/空值按模板降级规则处理（隐藏或占位），**不允许模板补文案**。
3. 同一 Resume JSON 对任意 ats/showcase 模板渲染，导出回读后的 Claim 集合做集合相等断言；在线载荷构建后做同样断言。
4. 内容编辑回写 Resume JSON（触发 Guard 复验，新版本）；排版编辑只写 render_params（不触发事实校验）。

## OnlineResumePayload（BOSS 在线四模块）

```json
{
  "advantage": "个人优势纯文本…",
  "work_experiences": [{"company_ref":"exp_1", "content": "职责与成果条目…"}],
  "projects": [{"project_ref":"prj_3", "content": "项目描述…"}],
  "skills": ["技能1", "技能2"]
}
```

约束：纯文本/换行/受控符号；各模块字数上限配置化；只含 `supported` 内容；不含 Inference；不含公司名/职位/起止时间/学历（平台资料字段，扩展永不写入）；技能仅取自规范技能且有证据或本人确认。构建后经 ATS 在线检查（专题 09）与扩展预检（专题 21）双检。

## Greeting Generator（v1.1 新增）

- **输入白名单**：该岗位 Raw Job 字段（jobName/brandName/salaryDesc/cityName 等受限变量槽）、投递建议中的 strong_evidence 引用、approved facts 摘要；**禁止注入 JD 之外的公司信息、聊天历史**。
- **输出**：每岗默认 3 条变体（不同侧重：证据强相关/岗位理解合规表达/简洁型），每条含 `text、slots_json、evidence_ids、variant_no、length_check、risk_flags`。
- **硬规则**：能力/成果陈述必须有 evidence_ids；禁止「我了解到贵公司…」类无来源了解、禁止薪资/到岗承诺、禁止无依据称谓（如“老师”可配置）、禁用绝对化用语；长度符合平台限制；变量槽渲染失败整条阻断而非留占位符。
- **A/B 与追踪**：变体随包冻结；用户选中写 `greeting_variant.selected_at`；未选变体保留；复盘按变体统计回复率（ADR-007）。
- 生成后只通过 `copy_greeting` 写入剪贴板/输入框，**系统不发送**。

## 编辑协作与版本

投递包页：Claim 的 Evidence 抽屉、字数、ATS 风险、版本 diff、模板切换预览、招呼语卡片。用户改正文创建 Claim revision 并触发 Guard；删 Claim 不删 Evidence；排版微调走模板参数。支持从 published `fork`、两版本 Claim 比较。禁止就地编辑已关联 Application 的版本；重发/新沟通必须派生新版本与新变体集。

## 质量控制

内容：具体情境/行动/可验证结果，避免无信息密度的“负责/参与”；招呼语逐条过禁用表达与证据检查。版面：页数预算、孤行、阅读顺序、中文字体、链接可点、语言一致性（渲染器与回读校验见 22/09）。ATS 版稳定解析优先，Showcase 版表达优先；渠道不可混用。
