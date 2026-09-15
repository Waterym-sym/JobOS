# 06 Candidate Intelligence 技术方案

> 版本：v1.1（新增知识库冷启动与本地迁移：Profile/work、career-kb、旧简历、引导录入）

## 定义

Candidate Intelligence 是本人的职业事实层，不等于某一份简历。它统一管理基本资料、教育、工作、项目、技能、成果、偏好和原始资产，区分用户确认事实与系统推断；同时负责 v1.1 冷启动：把既有的三个个人数据源迁入，并支持按 JD 缺口引导补录。

## 数据来源与写入原则

| 来源 | 写入对象 | 默认可信度 |
|---|---|---|
| 用户表单/引导录入 | Profile/Experience/Project | 已确认 |
| **`E:\Profile\work` 目录连接器** | Project/Artifact/Evidence/Experience | 项目经验文档=待确认事实；原始资料/代码=证据 |
| **career-kb 导出文件** | Profile/Experience/Skill/Evidence | 按原可信度 A-D 映射，C/D 需人工确认 |
| 旧简历文件（含 DOCX 导入） | Parsed Fact Candidate | 待用户确认 |
| 项目文档、代码、证书 | Artifact/Evidence | 证据，非自动履历事实 |
| 模型提取 | Inferred Fact | 仅建议，不能直接发布 |
| 聊天回采 | 不入事实层 | 仅复盘引用（见 07） |

导入流程：来源登记 → 类型/大小校验（本地文件免病毒扫描但仍做 MIME/魔数与解析沙箱）→ 文本/OCR 解析 → 字段候选 → **用户确认** → 索引。元数据保存 SHA-256、mime、解析版本、PII 级别、来源连接器与保留状态。

## 冷启动一：`E:\Profile\work` 目录连接器

只读扫描（不移动/不改写原件），约定结构映射：

| 目录/文件 | 映射 |
|---|---|
| `<项目>/项目经验.md`（八段式） | Project 的事实候选：按段落解析背景/职责/技术栈/行动/成果/量化数据/复盘，逐段生成 Claim 候选挂接原文锚点，**全部待人工确认** |
| `<项目>/原始资料/` | Artifact（文档/截图/表格），切片索引为 Evidence |
| `<项目>/源代码/` | Artifact（代码仓库），按路径/函数符号切片；默认剔除密钥、锁文件、二进制、vendor |
| `公司背景/` | Experience 的组织/行业/时间上下文候选 |
| `缺口补齐/` | Gap 记录（job-gap 报告）→ 进入引导录入队列，不生成能力 Claim |

**项目性质标记（诚信红线）**：每个项目必须标记 `nature=real_world|secondary_dev|learning_ref`。

- `real_world`（实战）：可正常支撑在职/成果 Claim；
- `secondary_dev`（二开）：必须保留开源许可与「基于 X 二次开发」表达，Claim 不得写成从零主导；
- `learning_ref`（学习参考/教程跟练）：**不得写成在职经历或商业项目**，仅能在「个人项目/学习」语境下表达，且 Evidence 置信上限下调。

连接器配置根目录、扫描计划（手动触发/开机后可选）、增量哈希；映射预览页逐项目确认。

## 冷启动二：career-kb 导出导入

career-kb 是 localStorage 静态应用（键 `career-kb-data`）。导入其 JSON 导出文件：

- `profile/experiences/skills/evidence` → 对应实体，保留原 ID 映射表；
- 可信度 A/B/C/D → 本系统 confidence：A=0.95、B=0.8、C=0.55、D=0.35；**C/D 不自动进 `confirmed`**，进入确认队列；
- 隐私级 S0–S4 → PII 级别映射，S3/S4 默认不进 Embedding、不进任何导出；
- 健康度/ JD 匹配结果作为只读参考标签，不迁入评分体系。

## 冷启动三：旧简历导入

PDF/DOCX/MD/图片（OCR）解析为 Fact Candidate；时间线冲突、无法定位的量化成果、与工作知识库矛盾项高亮。DOCX 走开源解析（与模板导入管线分离，避免简历内容被误当模板）。

## 冷启动四：JD 引导录入向导

以「缺口驱动问答」补录：选定目标 JD → Match 给出 missing/partial Requirement → 向导按项提问「是否做过？在哪个项目？有什么材料？」→ 回答落为自述事实（`self_reported`）或引导关联到已扫描的项目材料；补录后重新跑 Evidence Judge。缺口补齐目录中的旧 gap 报告自动作为问题来源之一。

## 职业画像与冲突检查

```text
Candidate Profile
 ├─ identity & preferences（地点、目标职位、薪资仅本机可见）
 ├─ experience / education / project（有时间线，含 nature 标记）
 ├─ skills（自述、证据支持；熟练度不用无依据星级）
 └─ artifacts → evidence（可追溯来源；连接器只读引用）
```

冲突检查：时间重叠、结束早于开始、证书号冲突、数字与证据冲突、学习项目被写成在职经历（阻断）。冲突不自动修复。编辑用乐观锁版本号并写本地审计日志。

## 事实生命周期

`observed → extracted → confirmed → superseded/retracted`。Resume/Match 默认只使用 `confirmed`；Judge 可引用 `observed` 原文但标识证据级别与项目 nature。撤回事实后关联 Claim 变需复验，不悄悄删改。

## 结构化字段要求

| 实体 | 最小字段 | 校验 |
|---|---|---|
| Experience | 组织、职称、开始/结束、职责、来源连接器 | ISO 月份；结束不得早于开始 |
| Project | 名称、角色、周期、性质 nature、问题/行动/结果 | 二开须有许可字段；量化结果有来源或标自述 |
| Education | 学校、学位、专业、时期 | 学位枚举+原文 |
| Skill | canonical/raw、场景、证据数、可信度 | 禁止仅用星级代表能力 |
| Preference | 目标角色、地区、通勤上限、工作方式 | 默认私密，不外发到简历 |

## 隐私（本地单机）

联系方式/地址/证件号标 PII，默认不进 Embedding；用户决定各字段进入哪个渠道版本。源目录只读引用，删除连接器引用不删原件。导出生成临时包并可一键清除；删除走「撤销索引与引用 → 保留期 → 物理清理」。

## 产品接口与可追溯性

每个字段显示来源徽标（手工/工作知识库/ career-kb /旧简历/模型建议/项目性质）与 source span。Profile revision：`PATCH` 需 `If-Match`；批量导入不覆盖较新的用户确认值。导入入口：`POST /kb/imports/{profile-work|career-kb|resume|guided}`，进度经 SSE 返回。
