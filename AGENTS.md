# AGENTS.md — AI 编程代理现场规则（本文件为硬红线，精简执行版）

本项目是 **AI Resume OS / JobOS**：求职闭环（BOSS 采集 → 筛选 → JD/匹配 → 人工候选 → 三形态简历+招呼语 → 人工发送 → 聊天回采 → 复盘）。**2026-09-18 已获本人架构裁决，目标改为多用户系统；现有代码仍处于单用户本机实现，不能因本规则更新而宣称多用户能力已交付。**公网入口只允许经独立人审、认证与隔离验收后启用；扩展采集/聊天回采仍限本机独立链路。

**动手前必读**：
- 架构与口径：`docs/AI-Resume-OS-JobOS-系统设计与技术架构方案-v1.0.md`（内容版本 v1.1）
- 架构检索入口：根目录 `AI-Resume-OS-架构师索引库-v1.0.md`（内容 v1.1）——接任务先按关键词检索 ARCH-* ID，任务单中列出引用的 ARCH ID/契约/ADR
- 开发基线/契约/DoR：`docs/architecture/23-开发基线与契约固化.md`
- AI 协作规范（解释版）：`docs/architecture/24-AI协作开发规范与边界.md`
- 风险与验收：`docs/architecture/20-风险与验收标准.md`；扩展协议：`docs/architecture/21-浏览器扩展集成协议.md`
- 机器契约：`contracts/`（ws / api / db / dsl / filters）

## 绝对禁止（生成即视为缺陷，扫描关键字并列）

1. 自动对外动作：`send_message`、`deliver`、`auto_apply`、`auto_greet`、自动点击沟通、自动上传附件；`auto_next_page` 恒为 `false`，禁止自动翻页。协议层不存在 send 类命令。
2. 放宽风控：节流下限不得低于 1800ms、禁止去掉抖动、并发恒 1、不得绕过 `capture.error{risk:true}` 暂停；禁止 hook 发送/已读接口，只允许被动读取。
3. 在线填充红线：公司名/职位名/起止时间/学历永不写入，载荷中出现也跳过并报 `skipped_redline`。
4. 聊天原文不出本机：不得进入第三方 LLM 请求、日志、错误上报；草稿事件 `review_status=draft` 禁止自动投影状态。
5. 禁止硬编码密钥/token/cookie；`.env`、`data/` 不得入库；禁止削弱 loopback/配对 token/Origin 校验与聊天加密。
6. 禁止无证据 Claim、Truth Guard 后门、学习项目写成在职经历、模板内写事实文本、showcase 静默进 ATS。
7. 禁止引入 Aspose 等商业库与 GPL/AGPL 类传染性许可依赖进默认栈；许可证存疑即停。
8. 禁止擅自修改既有 ADR、24 篇红线、验收阈值或本文件；禁止删除/跳过/弱化测试或 Gold Set；禁止自动调权/自动应用策略。本人已明确批准本次从单用户转多用户的架构规则修订与新增 ADR；其余修改仍须逐项授权、独立人审，既有安全阈值不因本次变更而降低。
9. 四个外部仓库只读，禁止任何修改：`E:\GitHub\boss-chorme`、`E:\GitHub\boss-helper-main\boss-helper-main`、`E:\GitHub\a4cv-main`、`E:\GitHub\resume-3d-orbit`。
10. 禁止超范围"顺手改进"、引入未批准框架/云组件。

## 必须遵守

- 检索先行：接任务先查根目录架构师索引库的 ARCH-* 条目，任务单写明 architecture_refs / contracts / red_lines（任务头模板见索引库 §8）；无适用条目先提新条目或 ADR 交人审。
- 契约先行：改接口先改 `contracts/` 与对应文档，再实现；`packages/contracts-py|ts` 为单向生成，禁止手改。
- 工作流：任务单 → DoR 核对（23 篇 §7 + 索引库 §4）→ 契约 → 最小实现 → 测试 → 自评清单 → **人工 Review 后才合并**；AI 不得自行合并/推主干。
- 每个新行为带测试；每条红线配「证明做不到」的测试（违禁 handler 注册失败、红线字段不写入、非 loopback 拒绝、出站不含 chat 字段）。
- 跨域、契约/DDL/迁移、Prompt/权重、配置默认值、扩展采集/解码/填充、安全/隐私/事实文案：🟡 必须人审。
- 日志结构化且禁打聊天原文/密钥；UTC 存储；WS 上报按 `source+ext_id`/`ext_msg_id` 幂等。
- 当前服务仍只绑 `127.0.0.1`。目标架构仅允许经认证、授权、TLS 和隔离门禁的 Web 入口对外；API/WS 扩展端、PostgreSQL、Redis、Worker、管理接口不得直接公开。任何用户拥有的数据库行、缓存、文件、后台任务均须由服务端确定归属并隔离；不得信任客户端传来的 owner/tenant 标识。
- 多用户架构文档与权限方案须先完成独立人工 Review，之后才可改认证、数据迁移与界面业务代码；公网部署另设 Go/No-Go，不因本地测试通过自动上线。

## 遇到以下情况立即停止并请人裁决

任务要求触碰任一禁止项；契约与文档冲突；测试与红线冲突；无法确认数据是否属于聊天 PII；许可证不确定。**宁可少做，不可绕行。**
