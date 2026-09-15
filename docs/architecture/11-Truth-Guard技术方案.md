# 11 Truth Guard 技术方案

> 版本：v1.1（守卫范围扩展：Greeting、在线载荷、模板渲染一致性、聊天信息隔离）

## 目标

Truth Guard 是投递包发布/使用前的事实安全门，不是文案润色器。v1.1 守卫四类对象：**Resume Claim、Greeting 变体、OnlineResumePayload、模板渲染一致性**。核心原则不变：实体、日期、数字、职责、技能必须由本人确认事实或有效 Evidence 支持。

## 规则与动作

| 规则 | 对象 | 结果 | 动作 |
|---|---|---|---|
| 无 Evidence / 引用已失效 | Claim、Greeting 能力陈述 | `unsupported` | 阻断发布/阻断该变体 |
| 数字、组织、日期与证据冲突 | Claim、Greeting | `contradicted` | 阻断并定位冲突 |
| 多段经历推算年限 | Claim | `derived` | 显示计算过程，需确认 |
| 「主导/上线/负责」缺乏支持 | Claim、Greeting | `partial` | 降级措辞或人工审核 |
| 新增技术/证书/学历/量化成果 | Claim、Greeting | `unsupported` | 拒绝并记录模型质量事件 |
| 虚构对公司业务了解/无来源赞美 | Greeting | `unsupported` | 阻断该变体（如“我了解到贵公司近期…”） |
| 承诺类表达（薪资/到岗/加班/独家） | Greeting | `banned_expression` | 阻断 |
| 红线字段出现在载荷 | Online Payload（公司/职位/时间/学历） | `redline_violation` | 阻断填充 |
| Inference/未确认事实进入载荷 | Online Payload | `unsupported` | 阻断 |
| 渲染后 Claim 集合与输入快照不一致 | 任一渠道导出版本 | `template_drift` | 阻断导出（模板不得改事实） |
| 模板槽位出现 Blueprint 外文本 | 导出件 | `template_fact_injection` | 阻断并标记模板缺陷 |
| 聊天信息被写入事实/证据 | Candidate/Evidence 写入 | `chat_as_evidence` | 拒绝写入（无例外路径） |
| 学习项目支撑在职/主导 Claim | Claim | `nature_mismatch` | 阻断 |
| 二开项目缺少许可/二开表述 | Claim | `license_missing` | 阻断，提示补充声明 |

## 实现

从 Claim/招呼语抽取实体、数值、时间、责任动词与公司指称；确定性比较优先（规则表、数值/日期比对、槽位白名单、变量槽渲染校验），语义判定再调受限 LLM，输出仅 `direct_support/partial_support/contradict/no_support`，不产生新事实。

模板一致性走确定性比对：`input_claim_set_hash` 与「渲染 → 独立解析器回读」得到的 Claim 集合做规范化后集合相等比较（渠道允许的格式化差异列入白名单，如标点/换行/全半角）。

发布/使用事务检查：简历版每条 Claim `supported` 且有 `claim_evidence`；被选招呼语变体所有事实性陈述有证据或属白名单变量槽；载荷零红线字段；模板一致性通过。否则返回 `RESUME_UNSUPPORTED_CLAIM` / `GREETING_UNSUPPORTED` / `PAYLOAD_REDLINE` / `TEMPLATE_DRIFT`。允许保留未通过的草稿，但禁止进入投递包使用。Guard 结果携带规则版本、模型运行、证据哈希、模板/渲染器版本。

## Claim 分类与风险矩阵

| Claim 类别 | 示例 | 默认证据门槛 |
|---|---|---|
| 事实 | 任职、学位、证书、技术使用 | 原始材料或确认事实 + 定位来源 |
| 量化结果 | 降低 40% 耗时 | 指标、基线/比较对象、来源齐备 |
| 责任 | 主导、设计、上线 | 项目职责/协作证据直接支持，且与 nature 相符 |
| 能力归纳 | 具备 RAG 应用经验 | ≥1 个直接项目 Evidence，强度匹配 |
| 偏好/目标 | 寻求 AI 应用职位 | 用户确认；不是历史事实 |
| 招呼语事实 | 「我做过 X，用了 Y」 | 必须回链 evidence_id；变量槽只取岗位字段 |

高风险词表：绝对化、唯一性、主导、规模/金额/百分比、年限、资格声明、招呼语中的「承诺/保证/随时到岗/期望薪资」。提高校验等级但不禁止真实强表述。

## 检查顺序

1. 解析实体/单位/日期/数字/责任谓词/变量槽；
2. 验证 Evidence 可访问、未删除、来源白名单（非聊天、非模板、非 JD）；
3. 项目性质封顶检查（nature_mismatch/license_missing）；
4. 确定性事实比对与禁用表达匹配；
5. 语义支持 Judge（仅给定证据）；
6. 载荷红线与字段来源检查；
7. 模板渲染后回读集合比对；
8. 聚合为不可变 Guard Run（含阻断项定位与建议替代表达）。

任一步失败不得默认通过；`verify_package` 对简历三渠道 + 全部招呼语变体一次性出报告。

## 人工例外与复盘联动

可标记「待补证据」但不能使用；没有绕过事实校验的通用后门；声明性字段显式 `self_reported` 且不得写成外部验证事实。聊天中的 HR 反馈（如“经验不匹配”）只进入复盘分析，不回写事实库。Guard 的误报/漏报按月从复盘结果抽样，更新规则版本；策略建议中涉及规则/阈值的修改仍需人工批准（ADR-008）。
