# P1-003 控制台外壳与页面地图

```yaml
task: P1-003-console-shell
status: ready_for_human_review
domain_owner: Web Platform
architecture_refs:
  - ARCH-BIZ-001
  - ARCH-API-001
  - ARCH-SEC-001
  - ARCH-NFR-001
  - ARCH-AIAGENT-001
contracts:
  - contracts/api/openapi.yaml
data_classification: internal
human_approval: required
nfr:
  - Node 20 LTS 与 pnpm 9 可重复构建
  - 页面地图全部路由可达
  - 小于 768px 明示只读模式
  - 前端构建产物不包含配对 token 或模型 Key
  - desk/ops/minimal 三主题可切换且持久化
acceptance_tests:
  - 今日案头与页面地图九区均可通过 hash 路由直接访问
  - 漏斗导航顺序符合主流程，辅助页面与业务管线分组
  - API 健康状态只使用真实 health 响应，不伪造扩展、AI 或备份状态
  - 每个未实现页面有解释当前状态和下一步的空态
  - UI 不存在自动发送、一键投递、自动翻页或自动上传控件
red_lines:
  - AGENTS.md 禁止项 1、4、5、6、8、10
  - 不新增或修改 API、WS、数据库契约
  - 不实现采集、填充、聊天、生成、上传或任何对外动作
```

## 目标

按 `DESIGN.md` 与 01 篇页面地图建立可导航的本地控制台外壳，为后续领域页面提供稳定路由、TopBar、FunnelNav、空态与响应式只读边界。本任务只呈现已经存在的 API 健康信息；没有状态源的数据一律标记为“未接入”，不以演示数字冒充事实。

## DoR 审计（2026-09-15）

| 检查项 | 证据 | 结论 |
|---|---|---|
| 架构检索 | 已核对页面地图、ARCH-BIZ-001、ARCH-API-001、ARCH-SEC-001、ARCH-NFR-001、ARCH-AIAGENT-001 | 通过 |
| 视觉真源 | 已完整读取根 `DESIGN.md`，并按其路由查阅 Linear/Vercel 参考 | 通过 |
| API DTO | 只消费现有 `/healthz`，不新增手写业务 DTO 或枚举 | 通过 |
| 数据来源 | 除 API health 外均无真实状态源，因此不显示业务计数或模拟记录 | 通过 |
| 契约/DDL/迁移 | 本任务不修改任何契约、DDL 或迁移 | 不适用 |
| 人工 Review | UI 与安全文案已完成，未提交、未合并、未推送 | 待人工 Review |

## 实现范围

1. 今日案头首页。
2. 主流程：采集中心、岗位池与筛选、候选区、投递包、事件确认台、复盘与漏斗。
3. 辅助页面：模板中心、知识库、设置。
4. 全局 TopBar、FunnelNav、页面空态、上下文边栏和移动端只读提示。
5. hash 路由解析与导航安全测试，不引入额外路由框架。

## 完成条件

- Web 测试、TypeScript 检查、生产构建与 Node 20 隔离复验通过。
- 页面截图完成桌面与移动端视觉检查。
- anti-slop、无密钥、无禁止动作扫描通过。
- 自评清单完成，状态改为 `ready_for_human_review`。

## 验证证据（2026-09-15）

- 路由：今日案头加页面地图九区共 10 个 hash 路由；7 个流程节点与 3 个辅助页面分组测试通过，未知路由安全回到今日案头。
- JavaScript/TypeScript：Web 12 项测试通过；类型检查与生产构建通过。
- 基线复验：在 Node 20.18.3 / pnpm 9.15.5 隔离容器中重复执行测试、类型检查和构建，全部通过。
- Container：`jobos-web` 镜像重建通过；生产容器首页返回 200，API 不可用时代理返回结构化 502。
- 视觉：桌面今日案头、桌面设置页、390×844 采集页完成浏览器截图检查；移动端出现只读提示，导航与状态信息可读。
- Security：源码禁止动作扫描为 0；生产构建中配对 token、模型 Key 与私钥模式扫描为 0；无渐变 hero、衬线标题、插画或 emoji 图标。

## Pre-flight 与自评

1. 每屏至多一个墨色主操作；当前只有今日案头的“查看扩展接入”。
2. 当前无 AI 产出，因此不伪造草稿卡；后续 AI 内容必须从 `card-draft` 起步。
3. 当前无 Claim/JD 数据，因此不伪造证据数量；边界栏仅用 `●◐○ + 文字` 示范已定义的状态语言。
4. 没有对外动作，未实现或放置发送、投递、翻页、上传控件。
5. 除真实 API health 外，扩展、AI、备份均明确标为未接入或无记录。
6. 使用 DESIGN.md v1.0 三主题 token、无衬线/等宽字阶、4px 栅格和发丝线；组件不含硬编码颜色。
7. 所有导航与动作均为原生链接，键盘可达并有 2px focus ring；`prefers-reduced-motion` 禁用过渡。
8. `<768px` 明示只读，触控导航与主动作最小高度 44px。

## 人工 Review 关注点

- 本人已于 2026-09-16 确认工作区 `DESIGN.md v1.0`（desk/ops/minimal 三主题，desk 默认）为正式视觉真源；实现已按该定稿收敛。
- 七级 FunnelNav 将“今日案头”作为入口级，随后是采集、筛选、候选、投递包、事件确认、复盘；模板、知识库、设置独立分组。
- 当前设置页是只读安全基线，不保存任何浏览器配置；后续编辑能力必须先补受校验的本机 API 契约并单独人审。
