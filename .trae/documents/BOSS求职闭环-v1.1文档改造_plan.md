# AI Resume OS v1.1 文档改造（BOSS 求职闭环 + 简历模板系统）实施计划

## 一、仓库研究结论

### 1. 现有 v1.0 文档现状

`docs/` 下共 22 份文档：1 份总体方案（`AI-Resume-OS-JobOS-系统设计与技术架构方案-v1.0.md`，18 章）+ `architecture/` 下 20 篇专题 + README 索引。

v1.0 已覆盖闭环：`手工 JD → 岗位画像 → Evidence 匹配 → Fit/Gap/Risk → 定制简历 → ATS 检查 → 人工投递记录 → 离线校准`，定位是**多租户 SaaS**（FastAPI + PostgreSQL/pgvector + Redis + S3 + K8s，OAuth/RLS，1000 MAU）。Resume 侧只有"ATS/Showcase 双模板"概念，**无可选模板库、无可视化编辑器、无 DOCX 模板导入**。

与本次目标相比，v1.0 的 8 个缺口：

1. **采集接入缺失**：JD 仅支持粘贴/受控 URL/手工录入；"市面职位大规模抓取"在 19 篇中被明确列为延后项。
2. **批量筛选漏斗缺失**：只有单 JD 匹配，没有"岗位池 → 条件初筛"阶段。
3. **候选区决策缺失**：没有 shortlist（候选区）实体与人工确认环节。
4. **打招呼语缺失**：20 篇无任何 first-contact message 设计。
5. **沟通/面试状态回传缺失**：Application 状态机为 `saved→submitted→viewed→interviewing→offer|rejected|withdrawn`，无"已打招呼/已回复/沟通拒绝/约面/面试拒绝"等 BOSS 实际阶段，也无聊天原文。
6. **复盘能力薄弱**：ADR-003 限定"结果学习先只做观测与离线校准"，无单岗复盘、阶段汇总与策略反哺。
7. **简历模板系统缺失**：无模板库、无内容/布局/风格正交模型、无 DOCX 模板导入与可视化编辑。
8. **个人本地形态缺失**：全部按云 SaaS 编写（RLS/OAuth/K8s/WAF/配额），与个人单机使用不符。

### 2. 两个浏览器扩展参考

#### 2.1 boss-chorme（E:\GitHub\boss-chorme，自有插件）

| 能力 | 现状 |
|---|---|
| 列表/详情批量抓取 | 已有：公司、岗位、薪资、城市、经验、学历、行业、规模、融资阶段、list_tags、jd_text、skill_tags、detail_json（bossName/companyDesc/address），1.8s+随机间隔风控 |
| 本地存储 | Node HTTP 服务（127.0.0.1:**8789**）写 MySQL（`boss_jobs`、`batch_runs`，按 ext_id upsert） |
| JobOS 桥接 | MV3 service worker 已实现 WS 客户端连 `ws://127.0.0.1:8788/ws`，指令：`auth_ping/capture_list/capture_details/abort`；事件：`job.captured/job.updated/capture.phase/capture.completed/capture.error` |
| TS 核心流水线 | Work Pattern 引擎（jobProfile/workPattern/evidenceMatcher/resumeGenerator/scorer 四维评分），与主系统的 JD Intelligence + Matching + Resume Engine **职责重叠** |
| 在线简历填充 | 已有：BOSS 在线简历页四模块（个人优势/工作内容/项目描述/技能），人工确认后写入，不改公司名/职位/时间/学历；不上传附件 |
| 打招呼语 / 聊天采集 | **均无** |

#### 2.2 boss-helper（E:\GitHub\boss-helper-main，WXT+Vue3 开源参考，仅学习不抄代码）

- **有序筛选工作流**（`useApplying/handles.ts`）：已沟通去重 → 相同公司/相同 HR 去重（持久化 Set 带过期）→ 岗位名关键词白/黑名单 → 公司名关键词 → 薪资范围（解析 K/元时/元天/元月，区分时薪日薪）→ 公司规模 → 猎头过滤 → 详情获取 → **BOSS 活跃度**（activeTime，超 7 天/月/年淘汰）→ HR 职位黑白名单 → 工作地址关键词 → 好友状态 → 工作内容关键词（正则排除否定语境与"系统/软件/工具/服务"后缀）→ 金牌面试官 → 高德通勤距离/时间 → **AI 筛选打分**（rating 阈值）。
- **投递与打招呼**：`sendPublishReq`（一键沟通 API）；自定义招呼语支持 `renderTemplate` 模板变量（jobName/brandName/salaryDesc/cityName…）与多段消息；另有 AI 招呼语。**本系统不自动投递、不自动发送**，但其变量槽与数据字段可直接借鉴。
- **聊天解码**：自带 `chat.proto`（BOSS `cn.techwolf.boss.chat` protobuf：文本/图片/语音/视频/`TechwolfInterview` 结构化约面消息/系统通知/文章/动作）与 `geek-chat-core` SDK 封装——证明聊天/约面/通知可在扩展内通过**网络层解码**获得，比纯 DOM 抓取可靠。
- **统计**：按日计数（success/total/repeat/activityFilter/各任务淘汰数）+ 历史，验证了漏斗统计的字段口径。
- **数据字段**：薪资有 lowSalary/highSalary 数值域；岗位有 `atsDirectPost`（是否 ATS 直投岗，影响投递包策略）；boss 数据含 hasInterview/isFriend/isHeadhunter。
- **风控警示**：README 明示黑号/封号/降权风险——强化本系统"人工触发一切对外动作"的红线。

### 3. 简历模板两个参考

#### 3.1 a4cv（E:\GitHub\a4cv-main，PolyForm-Noncommercial 非商业许可，仅个人使用/借鉴设计）

本地优先纯静态 A4 简历工作台：**34 套风格预设 × 14 种布局 × 8 一键样式 × 16 配色 × 12 章节标题样式 × 20 类内容模块**；内容/布局/风格正交；模块拖拽排序与跨栏、头像形状/缩放、字号/密度/页边距、自动压缩一页、两页模式；导出 PDF/PNG/JPG/HTML/Markdown/打印；DOCX 导入（mammoth）；localStorage 多档案；AI 润色（DeepSeek/OpenAI 兼容，Key 仅存本地）；isomorphic-git 式简历分支与 diff。

#### 3.2 resume-3d-orbit（E:\GitHub\resume-3d-orbit）

- **224 套 DOCX 免费模板**（`docx/` 下 jpg 缩略图 + docx），3D CSS 环绕画廊与多维筛选（类型/职业 17 类/风格/语言 + 搜索，维度内 OR、维度间 AND），多页 3D 翻页预览。
- **模板管线**：`DOCX → extract_to_json（aspose/openxml 两种引擎）→ Template JSON v2 blueprint（绝对定位元素/样式/图片）→ normalize_blueprint → jsonv2_to_html（A4 HTML fragment）→ 编辑器 block 化`；Flask server 按 key 存储 source.docx/meta。
- **三栏编辑器 PRD**：25 个内容模块（5 大类、字段/显隐/排序/自定义标题/字段级显隐）、23 种布局（4 大类）、34 种风格，三者正交；模块与模板联动（ATS 风格自动隐藏照片/二维码模块）。
- **Dify/Coze 式生成工作流**：开始→选模板→个人知识库→岗位 JD→AI 分析→生成简历→导出，与本系统 Workflow 编排天然对齐。
- **技术包袱**：Aspose.Words 为商业库（`scripts/aspose/` 仅实验），默认方案采用开源 python-docx/openxml，复杂视觉版式回填会降级；224 套模板解析质量参差，需人工筛选。

### 4. 知识库冷启动数据源（已实地确认）

- **`E:\Profile\work`**：按项目组织的个人工作知识库。每项目含 `原始资料/`、`源代码/`、`项目经验.md`（8 段式）；另有 `公司背景/`、`缺口补齐/`（job-gap 报告）；项目分**实战/二开/学习参考**三类，自带诚信红线（二开许可声明、学习项目不得写成在职经历）。
- **`E:\GitHub\career-kb`**：纯 Node 静态小应用（端口 4321），数据存浏览器 localStorage（键 `career-kb-data`），模型含 profile/experiences/skills/evidence、可信度 A-D、隐私级 S0–S4、健康度、JD 匹配、简历版本。
- 另支持：**旧简历文件导入**、**按 JD 引导手工录入 + 文件导入**。

## 二、已确认的目标决策（用户提问结论）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 产品形态 | **个人本地单机版**，只服务本人；Docker Compose 本地运行 |
| 2 | 技术栈分工 | **采集端重写并入主系统**：插件只保留浏览器侧能力；主系统（Python/PG 生态）接管 8788 WS 服务端；Node+MySQL(8789) 废弃，老数据一次性迁移 |
| 3 | 自动化边界 | 批量采集+条件筛选自动；JD 分析/匹配/ATS 建议自动跑，**人工确认进候选区**；自动生成简历+打招呼语，**插件一键填充、人工点击发送**（不做自动发送）；自动回采状态+AI 复盘 |
| 4 | 状态采集 | **连聊天原文一起采集**，仅本地存储，供 AI 复盘引用 |
| 5 | 筛选条件 | 硬条件 + 公司画像 + JD 内容 + 去重频控（四类全要），并吸收 boss-helper 已验证维度：BOSS 活跃度、HR 身份（猎头/金牌/职位黑白名单）、同 HR、好友状态、薪资数值域、通勤距离（高德 Key 可选） |
| 6 | 打招呼语 | **每岗多条 A/B 候选**（支持受限模板变量槽），记录实际使用哪条，用于复盘话术效果 |
| 7 | 简历形态 | **BOSS 在线简历填充载荷 + ATS 附件 + 可视化模板版**，共享同一套溯源 Claim |
| 8 | 复盘 | 单岗复盘 + 阶段汇总 + **AI 策略建议**（筛选/打招呼模板/简历侧重/模板选择），人工审核生效，不自动调权 |
| 9 | 效果目标 | 不承诺"保证沟通/约面"；以**漏斗指标可观测**表达：采集→初筛→候选→打招呼→回复→约面→Offer |
| 10 | KB 冷启动 | 迁移 `E:\Profile\work` + `E:\GitHub\career-kb` 导出数据 + 旧简历导入 + JD 引导手工录入 |
| 11 | 渠道 | BOSS 先行，数据模型预留 `source` 渠道字段 |
| 12 | 模板资产 | **精选内置 ATS/可视化模板 + DOCX 导入管线（开源引擎）**；resume-3d-orbit 的 224 套按需批量导入（含缩略图、解析质量标记） |
| 13 | 模板界面 | **简洁网格模板库（默认）+ A4 可视化编辑器 + 3D 画廊/翻页预览（可关闭增强）** |
| 14 | 模板导出 | **PDF/PNG/HTML + DOCX（python-docx，复杂版式降级为 ATS 单栏）+ Markdown/纯文本** |
| 15 | 本次交付 | **仅文档**：修订总体 + 20 篇 + README + 新增第 21、22 篇；不写代码 |

## 三、v1.1 统一事实基线（各文档共用）

### 3.1 目标闭环

```text
插件批量采集(列表+详情)
  → 原始岗位池(captured, 去重指纹)
  → Stage-0 条件筛选(纯规则: 硬条件/公司画像/JD内容/去重频控/活跃度/HR特征; 淘汰留痕可捞回)
  → Stage-1 JD分析+Evidence匹配+ATS投递建议与依据(自动)
  → 人工确认 → 候选区(shortlisted)
  → 生成岗位专属投递包:
       ① 在线简历四模块载荷  ② ATS 附件简历(PDF/DOCX/MD)  ③ 可视化模板版(PDF/PNG/HTML)
       ④ 打招呼语 A/B 多条
  → Truth Guard(简历 Claim 与招呼语均须证据溯源)
  → 人工确认 → 插件填充在线简历/复制招呼语 → 人工发送
  → 聊天原文与状态回采(网络层 protobuf 解码为主, DOM 为辅; 事件草稿人工确认)
  → 终态单岗复盘(结合 JD/匹配/简历版本/模板/招呼语变体/聊天原文)
  → 阶段汇总(漏斗转化、拒绝原因、话术 A/B、模板效果)
  → 策略建议(人工审核生效, 不自动调权)
```

### 3.2 新增/调整领域对象

| 术语 | 含义 |
|---|---|
| Capture Source / Batch Run | 采集渠道（BOSS）与一次批量抓取会话 |
| Raw Job / Job Pool | 抓回的原始岗位（保留原文/JSON，与分析结果分层；含 low/highSalary、atsDirectPost 等扩展字段） |
| Filter Set / Screen Result | 筛选条件集与逐岗命中/淘汰原因（每条原因可定位到具体规则与字段值） |
| Shortlist（候选区） | 人工确认进入投递准备的岗位 |
| Application Package | 一个岗位的投递包：在线载荷 + ATS 简历 + 可视化版 + 招呼语变体集 |
| Greeting Variant | 打招呼语 A/B 候选（证据引用、受限变量槽、长度合规、selected 标记） |
| Chat Thread / Message | 沟通会话与原文消息（仅本地，最高 PII；含约面/通知等结构化类型） |
| Application Event（扩展） | greeted / chat_read / chat_replied / chat_rejected / interview_scheduled / interview_done / interview_rejected / offered / withdrawn；`source=extension/manual`、`confidence`、`review_status` |
| Retrospective | 单岗复盘与阶段汇总（不可变、版本化） |
| Strategy Suggestion | 复盘产出的筛选/话术/简历/模板调整建议，`proposed→approved|rejected→applied` |
| Resume Template | 模板 = 布局（Layout）+ 风格（Style/配色/字体/标题样式）+ 默认模块组合 + 槽位映射；不含业务事实 |
| Template Blueprint | DOCX 导入归一化后的元素/位置/样式 JSON 与内容槽位绑定 |
| Content Module | 25 类简历信息单元（字段级显隐、排序、自定义标题） |

### 3.3 新增 ADR（写入总体与 01）

- ADR-005 个人本地单机 + 浏览器扩展为唯一采集/执行端；服务仅监听 loopback。
- ADR-006 聊天原文仅本地存储，默认不进第三方模型上下文（脱敏开关可配）。
- ADR-007 打招呼语每岗多变体 A/B，记录被选变体用于复盘。
- ADR-008 复盘只产出策略建议，人工审核后生效；样本不足不自动调权（延续 ADR-003）。
- ADR-009 系统不自动投递/不自动发消息/不自动翻页；一切对外动作人工触发（账号风控红线）。
- ADR-010 模板只承载呈现、不承载事实；内容/布局/风格正交；ATS 模板与 Showcase 模板渠道边界不可混用。
- ADR-011 DOCX 模板导入仅采用开源解析（python-docx/openxml），Aspose 商业库不进默认发行栈；复杂版式允许降级。
- ADR-012 聊天回采用扩展网络层解码（参考 geek-chat-core/chat.proto）为主、DOM 为辅；自动分类只生成事件草稿，须人工确认入账。

## 四、文件与修改清单（共 24 个文件）

总体文档**原地升级为 v1.1**（文件名保留维持链接稳定，文首加版本与变更说明）；20 篇专题逐篇修订；README 更新；新增 21、22 两篇。

### A. 总体与索引（3）

- `docs/AI-Resume-OS-JobOS-系统设计与技术架构方案-v1.0.md`（原地升级，标题改 v1.1）：定位改为"个人本地职业资产操作系统 + BOSS 求职闭环 + 简历模板系统"；目标增加漏斗指标；角色=本人 + 扩展 Service Account；非目标改写；业务架构增加 Capture/Pool Screening/Outreach/Retrospective，Resume 域拆出 Template 子域；技术架构改本地 Compose（含 HTML→PDF 渲染组件、模板存储）；时序增加采集筛选、模板渲染与回采复盘；ER 增加新实体与模板表；API 增加 WS/模板/池化资源；部署/监控/排期/风险/验收按本计划改写；补 ADR-005~012。
- `docs/architecture/README.md`：版本 v1.1；索引增加 21、22 篇与评审主责；统一约束增加"不自动发送/投递、聊天数据不出本机、筛选只建议不替人决策、模板不承载事实"。
- `docs/architecture/21-浏览器扩展集成协议.md`（**新增**）：见第五节大纲。
- `docs/architecture/22-简历模板与渲染引擎技术方案.md`（**新增**）：见第六节大纲。

### B. 20 篇专题逐篇改动

- **01 系统设计文档**：闭环公式扩展为 3.1 全链路；目标表加"触达/漏斗"；角色精简；领域表加 Capture/Screening/Outreach/Retrospective 与 Template 子域；MVP 范围更新；场景增加批量采集筛选、候选区确认、打招呼 A/B、模板选择/编辑、状态回采、复盘；业务规则补充；补 ADR-005~012。
- **02 技术架构设计**：基线改为**本地优先模块化单体**：Docker Compose（FastAPI + PostgreSQL/pgvector + Redis + Worker + WS:8788 + Web 静态 + MinIO/本地 FS + **HTML→PDF/DOCX 渲染组件与中文字体**）；插件 loopback 接入；鉴权改本地配对 token；个人规模容量；保留 Provider Adapter/Outbox/幂等；模板渲染为独立无状态组件，支持任务队列化。
- **03 业务流程设计**：主流程图重画；新增四段交互契约（批量采集与筛选、候选区确认、投递包生成含模板选择与人工发送、回采与复盘）；制作简历环节插入"模板库选择→可视化微调→导出"；Job/Application 状态机扩展；事件词表新增 `job.captured/screen.completed/shortlist.confirmed/template.selected/greeting.generated/application.greeted/chat.event_received/retrospective.generated/strategy.proposed`。
- **04 Workflow 编排设计**：标准流程改为 `ingest_capture → screen_filter → parse_jd → retrieve_evidence → calculate_match+ats_advice → [human:候选区确认] → plan_resume → (parallel: render_ats/render_showcase/build_online_payload/generate_greetings) → truth_guard → [human:发送/填充]`；回采事件驱动；终态触发 retrospective；岗位池批量 fan-out；审批节点=候选区确认/发布确认。
- **05 JD Intelligence 技术方案**：输入源增加扩展结构化采集（jd_text/skill_tags/明文字段/薪资数值域/atsDirectPost）；`source=boss` 预留；批量解析与去重指纹；需"详情后才能得到"字段（活跃度/HR 特征）单独标注来源阶段。
- **06 Candidate Intelligence 技术方案**：新增"知识库冷启动与迁移"章：①`E:\Profile\work` 目录连接器（八段式项目经验→Project/Fact；原始资料/源代码→Artifact；公司背景→Experience；实战/二开/学习参考标记与表达红线；缺口补齐→Gap 记录）；②career-kb localStorage 导出文件导入（可信度 A-D、隐私 S0-S4 映射）；③旧简历导入；④按 JD 引导录入向导（缺口驱动问答补录）。
- **07 Evidence OS 技术方案**：新增本地文件夹/代码目录导入索引策略；明确聊天原文**不作为** Claim 证据；学习参考项目证据不得支撑在职能力 Claim；模板内容（DOCX blueprint）不进入证据库。
- **08 Matching Engine 技术方案**：明确两阶段。**Stage-0 筛选器（纯规则，不调 LLM）**：硬条件（城市/薪资数值域/学历/经验/岗位名）、公司画像（行业/规模/阶段/黑名单/外包猎头/HR 职位黑白名单/金牌）、JD 内容（关键词白黑名单含否定语境正则/必备技能覆盖/JD 完整度/发布时间）、去重频控（同公司/同 HR/已沟通/已投递/已拒绝/JD 指纹）、BOSS 活跃度、好友状态、可选高德通勤距离；列表字段先筛、详情字段按需二次筛（注明节流）；AI 打分仅作为可选附加条件。**Stage-1 评分匹配**沿用现有模型；产出"ATS 投递建议与依据"（建议/谨慎/不建议 + 逐项引用）；淘汰可解释、可人工捞回；漏斗计数口径在此定义（与 18 篇共用）。
- **09 ATS Simulator 技术方案**：保留附件解析检查；新增 BOSS 在线载荷检查（四模块字数/字段红线/Inference 不入载荷/技能交集）；与第 22 篇模板体系对齐：**ATS 模板族**必须通过解析矩阵，**Showcase 模板族**只用于展示渠道，系统在选用时给出渠道提示；招呼语渠道合规检查指向 10/22。
- **10 Resume Engine 技术方案**：同一 Claim 集合三种渲染——ATS 文档、`OnlineResumePayload`、可视化模板版（**模板机制全部引用第 22 篇**，本篇只定义 Claim→槽位映射契约）；新增 Greeting Generator（A/B 多变体、受限变量槽白名单、证据引用、字数/禁用表达、selected 追踪）；人工编辑边界：内容改动走 Claim 复验，排版改动仅写模板参数。
- **11 Truth Guard 技术方案**：守卫扩展到 Greeting（能力/成果陈述须有证据、禁止虚构对公司业务了解、禁止无依据称谓承诺）；在线载荷边界；聊天信息不得自动成事实；**模板排版变化不得改变 Claim 文本与证据链**的守卫规则。
- **12 数据库设计**：单用户本地模型；新增表 `capture_source、batch_run、raw_job、filter_set、screen_result、shortlist、greeting_variant、chat_thread、chat_message、retrospective、strategy_suggestion`；模板相关 `resume_template、template_blueprint、template_import_batch、template_pack`；`resume_version` 增 `template_id、layout/style 参数快照、channel(ats/showcase/online)`；`application_event` 扩展类型与 source/confidence/review_status；chat 表最高 PII 仅本地；老 MySQL → PG 字段映射；模板 DOCX/缩略图存对象存储。
- **13 API 接口设计**：本地 token/loopback 约定；新增 REST：`/captures/*、/pool/jobs、/filter-sets、/screening-runs、/shortlists、/applications/{id}/package、/greetings、/chat-events、/retrospectives、/strategy-suggestions、/kb/imports/*`；模板：`/templates`（多维筛选搜索）、`/templates/import-docx`（批量+单导入，返回解析质量）、`/templates/{id}/render|preview`、`/resume-versions/{id}/editor-state`；WS 8788 总览指向 21 篇。
- **14 AI 模型与 Prompt 设计**：Agent 新增 Screen Analyst（规则为主）、Greeting Writer（多变体+变量槽白名单）、Retrospective Analyst（可访问聊天原文与投递包，无写事实权限）、**Template Advisor**（按职位族/渠道/内容量推荐布局与模板）；聊天上下文默认不出本机；新增 4 类 Prompt 模板与评估集。
- **15 Workflow DSL 设计**：换新示例（采集→筛选→候选→并行渲染/招呼语→守卫→人工→回采复盘）；静态门禁：禁止注册外部消息发送/投递 handler；greeting 节点须前置 evidence/match；render 节点声明 channel 与 template_id；chat 事件走事件入口。
- **16 测试与评估方案**：Gold Set 增加筛选规则集（含 boss-helper 式边界：时薪日薪、否定语境、活跃度）、招呼语溯源合格率、聊天事件分类（约面/拒绝）准确率、复盘抽检、**模板槽位映射正确率、DOCX 导入成功率与版式保真度、ATS 模板解析率、导出一致性（PDF/DOCX/MD 三态字段一致）**；E2E 用例覆盖完整漏斗与模板选择；扩展协议契约测试；三类 KB 迁移测试。
- **17 部署架构**：替换为 Windows 本地 Docker Compose（端口表含 WS 8788/API/Web）；渲染依赖（Chromium/WeasyPrint、python-docx、中文字体卷）；扩展未打包加载；模型走用户自有 Key 或本地模型；备份=pg_dump+本地目录+Profile 只读引用；模板资产（224 套可选导入）磁盘预算说明。
- **18 监控与运维方案**：本地健康检查 + **求职漏斗仪表盘**（采集/初筛/候选/打招呼/回复/约面/Offer、淘汰原因分布、A/B 变体回复率、模板使用与导出成功率）+ 扩展连接状态 + token 成本；新增指标：模板渲染失败率、DOCX 导入失败率；Runbook：登录失效/风控、WS 断连、选择器/接口变更、聊天解码失败降级 DOM、Provider 不可用、备份恢复。
- **19 项目实施计划**：按依赖与 DoD 重排（个人/小团队，无日历排期）：P0 文档+数据/协议契约 → P1 本地骨架+扩展重写（弃 8789）→ P2 采集+筛选+JD/匹配 → P3 模板系统（内置模板+DOCX 导入+网格库+编辑器+导出） → P4 三形态简历+招呼语+在线填充 → P5 聊天回采+事件 → P6 复盘+漏斗+策略建议；各阶段出口门禁。
- **20 风险与验收标准**：风险新增 BOSS 风控/封号、插件接口变更、聊天隐私、单机数据丢失、第三方模型泄露、**第三方 DOCX 模板版权（仅限免费授权/自有模板）、Aspose 商业许可误用、复杂模板版式降级、可视化模板被误用于 ATS 机筛渠道**；验收：真实本地样本跑通全漏斗、溯源 100%、聊天不出本机、无自动发送路径、ATS 模板解析率达标、DOCX 导入与多格式导出可复核、漏斗仪表盘数字可对账。

## 五、第 21 篇《浏览器扩展集成协议》大纲

1. **拓扑与配对**：MV3 扩展 ↔ `ws://127.0.0.1:8788/ws`（沿用现有 JSON 信封 v:1/kind/id/type/payload）；REST 回退；配对 token；loopback + origin 校验。
2. **扩展重写后职责边界**：只保留 DOM/网络能力（列表抓取、详情抓取、**聊天采集**、在线简历填充、侧栏展示）；废弃 MySQL 8789 链路与 TS 评分生成核心（jobProfile/workPattern/evidenceMatcher/resumeGenerator/scorer），分析生成全部在主系统；侧栏渲染主系统视图；参考 boss-helper 的工程组织（任务注册表、按日统计）但不引入其自动投递。
3. **命令协议**：沿用 `auth_ping/capture_list/capture_details(detail_limit/delay_ms)/abort`；新增 `fill_online_resume`（四模块 payload+预检+当场确认）、`copy_greeting`（写入剪贴板/输入框，**无发送指令**）、`capture_chat`（会话增量拉取）。
4. **事件协议**：沿用 `capture.phase/job.captured/job.updated/capture.completed/capture.error`；新增 `chat.event`（thread/message/类型/分类草稿/置信度）、`fill.completed`；风控词（账户异常/安全验证）即 `capture.error{risk:true}` 暂停。
5. **岗位数据契约**：对齐现 `boss_jobs` 字段并扩展 lowSalary/highSalary、atsDirectPost、activeTime、boss(isHeadhunter/isFriend/hasInterview/title) 等；注明列表可得 vs 详情可得。
6. **聊天采集方案（重点）**：**网络层解码为主**——hook 扩展内 BOSS chat SDK/接口响应，参照 `chat.proto`（TechwolfInterview 约面、Notify 通知、Image/Sound/Video/Article）解码；DOM 读取为辅；输出 thread/message 标准结构与状态分类草稿（已读/回复/约面/沟通拒绝/面试拒绝/Offer），全部带置信度、待人工确认；只采集不发送。
7. **风控红线**：间隔+抖动、抓取不翻页、登录态/风控检测即停、**不自动发消息、不自动投递、不自动上传附件**、在线填充必须当场确认；参考 boss-helper 封号警示写明用户承担账号风险。
8. **隐私安全**：聊天原文仅发 loopback、默认不外发第三方；最小 host 权限；token 轮换。
9. **迁移兼容**：老 MySQL `boss_jobs/batch_runs` 一次性导入映射；协议版本协商。

## 六、第 22 篇《简历模板与渲染引擎技术方案》大纲

1. **定位与边界**：模板决定**呈现**、绝不承载事实；同一 Resume Claim 集合可渲染 ATS 版/Showcase 版/在线载荷；Showcase 不承诺机器解析，选用时渠道提示（与 09 联动）。
2. **正交模型（吸收 a4cv 与 resume-3d-orbit PRD）**：Content Module（25 类、字段级显隐/排序/自定义标题）× Layout（23 种、栏宽/密度/边距/单双页参数）× Style（34 预设、配色/字体/标题/标签/装饰/头像形态）；模板=Layout+Style+默认模块组合+槽位映射，参数可复盖并随 Resume Version 冻结。
3. **模板库与检索**：元数据维度（类型 社招/校招/实习/应届、职业 17 类、风格、语言、色系、单双栏、页数、渠道 ats/showcase、免费授权、解析质量等级）；默认简洁网格库（多维 tag：维度内 OR、维度间 AND + 搜索）；3D 环绕画廊与翻页预览为可关闭增强（参考 resume-3d-orbit，默认关闭，契合简洁偏好）。
4. **DOCX 模板导入管线**：`DOCX → 开源解析(python-docx/openxml) → 元素/样式抽取 → Template JSON v2 Blueprint → 归一化 → 内容槽位绑定 → 缩略图 → 解析质量分级 → 人工确认入库`；批量导入 224 套（任务化、可断点、失败报告）；**Aspose 仅实验环境，不进默认栈（ADR-011）**；模板版权字段与来源记录，仅限免费授权/自有模板。
5. **渲染引擎**：Resume JSON + 模板参数 → 语义 HTML（A4 分页/中文字体/图片本地化）→ PDF（Chromium 打印或 WeasyPrint）/PNG/HTML；DOCX 走 python-docx 模板回填，复杂视觉版式降级到 ATS 单栏并显式告知；Markdown/纯文本由 Claim 直接序列化；导出后独立解析器回读校验（与 09 共用）。
6. **可视化编辑器**：三栏（模块库/模板库 ｜ A4 所见即所得画布 ｜ 属性与 Claim 抽屉）；拖拽排序/跨栏、显隐、风格配色字体微调、头像、自动压一页/两页；**内容编辑=Claim revision→Guard 复验；排版编辑=模板参数，不触碰事实**；编辑器状态保存与 Resume Version 绑定；参考 a4cv 交互但风格从简。
7. **版本与数据模型**：模板版本化、收藏/复制预设/停用；Resume Version 冻结 `template_id+template_version+全部渲染参数+claim 快照+renderer 版本+输入输出 hash`；与 12 篇表结构一致。
8. **模板推荐（Template Advisor）**：按渠道（BOSS 在线/附件/其他）、职位族、内容量（模块数量/篇幅）规则优先推荐；ATS 附件默认单栏模板；推荐可拒绝，不自动替用户决定。
9. **质量与测试**：槽位映射正确率、空白页/溢出/乱码/孤行检查、PDF↔DOCX↔MD 字段一致性、缩略图与正文一致性、导入回归集；中文排版与字体基线。
10. **非目标**：不做在线协同模板市场、不做模板付费、不做完全自由拖拽的设计软件（仅在受控布局网格内编辑）。

## 七、实施步骤（批准后执行）

1. 建 TodoList；总体文档原地升级 v1.1（含 ADR-005~012、新闭环、术语表、模板子域），作为一致性锚点。
2. 新增 21、22 两篇（协议与模板契约先行，供 12/13/09/10 引用）。
3. 修订 01–05（系统/技术/流程/编排/JD）。
4. 修订 06–11（冷启动、Evidence、两阶段筛选、ATS、Resume+Greeting、Guard）。
5. 修订 12–15（数据库、API、AI/Prompt、DSL）。
6. 修订 16–20（测试、部署、监控、实施、风险验收）。
7. 更新 README 索引与统一约束。
8. 全文一致性校验：术语/状态机/事件名/API/表名/ADR/漏斗口径跨篇统一；交叉链接与 Mermaid 语法检查。

## 八、依赖与注意事项

- 本次**只改文档**，不改 boss-chorme、boss-helper、a4cv、resume-3d-orbit 任何代码；外部项目仅作设计参考，且注意许可边界（a4cv 为 PolyForm-Noncommercial、boss-helper 仅供学习、224 套 DOCX 仅限免费授权个人使用）。
- 总体文档保留原文件名，文首标注 v1.1 与变更摘要；v1.0 经 git 历史回溯。
- 沿用 v1.0 核心不变量（分层保存、Evidence→Claim 溯源、历史不可变、AI 留痕），新增约束不得削弱。
- 诚信红线与 `E:\Profile\work` 既有规则对齐（二开/学习项目表达限制写进 06/07/11）。
- "保证被沟通/约面"在所有文档统一表述为**可观测、可复盘、可持续改进的漏斗目标**，不做结果承诺。
- 用户偏好简洁界面：3D 画廊为默认关闭的可选增强，模板库默认网格、编辑器控件克制。

## 九、验证方式

- 逐篇对照本计划第二节 15 条决策与 3.1 闭环检查覆盖度。
- 一致性扫描：多租户遗留表述（RLS/OAuth/K8s/MAU/S3 公有云等）均改写或标注；事件名、状态名、表名、API、ADR、漏斗口径跨篇一致。
- 协议可落地性：第 21 篇与 boss-chorme 现有 `jobos-bridge.js`/`schema.sql` 及 boss-helper 的 `chat.proto`/handles/requests 逐一对照，"沿用/新增/废弃"三类标注完整。
- 模板可落地性：第 22 篇管线与 resume-3d-orbit 现有脚本、a4cv 正交模型对照，开源依赖与商业依赖边界清楚。
- 链接与 Mermaid 检查；交付物复核：总体 1 + 专题 20 + README 1 + 新增 2 = **24 个文件**。

## 十、风险与应对

- **24 篇联动口径漂移** → 总体先定锚点与术语表，最后统一 grep 校验。
- **个人版残留 SaaS 表述** → 每篇"替换/保留"标记，验证步骤专列遗留扫描。
- **协议过度设计** → 命令/事件严格分"沿用现有/新增"，新增项标注用途与风控约束。
- **模板功能膨胀成设计软件** → 第 22 篇明确非目标：受控布局内编辑、不做自由画布/模板市场。
- **商业许可风险（Aspose/a4cv/模板版权）** → ADR-011 与第 22 篇版权字段、20 篇风险登记明确。
- **范围蔓延到编码** → 交付仅文档；实现以 21、22 篇与 19 篇阶段划分为准，另行开工。
