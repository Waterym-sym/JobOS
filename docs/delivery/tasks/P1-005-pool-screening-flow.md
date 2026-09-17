# P1-005 岗位池 → 筛选池流转与筛选池三栏案卷

```yaml
task: P1-005-pool-screening-flow
status: ready_for_human_review
domain_owner: Screening / Capture / Console
architecture_refs:
  - ARCH-SCREEN-001   # Stage-0 纯规则、零 LLM、可解释、可捞回
  - ARCH-MATCH-001    # Fit/Gap/Risk 输出；改权重须人工批准
  - ARCH-GOV-002      # 进入候选区必须人工确认；系统不得自动应用策略
  - ARCH-RETRO-001    # 漏斗口径 captured → screened_pass → shortlisted
contracts:
  - contracts/api/openapi.yaml
  - migrations/versions/20260917_0004_screening_entry.py
data_classification: internal
human_approval: required
nfr:
  - 流转为内部状态迁移，不产生任何对外动作
  - 进入候选区只由人工点击触发（ARCH-GOV-002）
  - 岗位池列表与 enrich 重启重建均排除已流转岗位（无重复流转环路）
  - 新增 UI 仅使用 :root[data-theme] token，无颜色字面量
acceptance_tests:
  - 队列暂停时岗位状态仍按数据推导（不出现 paused）
  - 补全完成自动写入 screening_entry（幂等，一个岗位一行）
  - 已流转岗位不出现在 /api/v1/shortlist；dismissed 不回岗位池
  - promote/dismiss/revert 为唯一状态入口，非法迁移 409、未知条目 404
  - 筛选池右栏为明确的「未接入 · 待评分」占位，不产生任何评分数据
  - 契约测试断言错误码、enrich_state 枚举与 screening_status 枚举
red_lines:
  - AGENTS.md 禁止项 1、6、8、10
  - 不改 ADR、AGENTS.md、24 篇红线、验收阈值；页面地图（01 篇）变更随本任务人审
  - 聊天原文不出本机；不引入 LLM 调用或权重
```

## 目标

把「岗位池」与「筛选池」拆成两段：岗位池补全完成（详情页 + 公司页）的岗位自动流入筛选池并从岗位池消失；筛选池提供三栏案卷（左列表 / 中 A4 案卷 / 右评估与决策）与人工的「进入候选区 / 忽略」；候选区做最小可用的候选列表与退回。同时把「导入扩展导出的岗位列表」迁到采集中心，并让队列暂停不再污染单个岗位的补全状态。

## DoR 审计（2026-09-17）

| 检查项 | 证据 | 结论 |
|---|---|---|
| 架构检索 | 已核对 ARCH-SCREEN-001、ARCH-MATCH-001、ARCH-GOV-002、ARCH-RETRO-001 与 01、12、14、20、21、23、24 篇 | 通过 |
| 机器契约 | `contracts/api/openapi.yaml` 先改（错误码、ScreeningEntryItem、4 个端点），再实现 | 通过 |
| 数据 owner/PII | `screening_entry` 归 Screening；只引用 `raw_job` 主键，不含聊天 PII | 通过 |
| 迁移策略 | Alembic 唯一入口；0004 的 downgrade 由 P1-006 补齐并在隔离库往返验证；不修改 baseline 骨架 | 待人审 |
| 安全策略 | 新端点沿用 loopback + Bearer；无新对外动作；只有人工 POST 可推进候选 | 通过 |
| 人工 Review | DDL、契约、页面地图、DESIGN.md、错误码均为 🟡 | 必须 |

## 范围

1. 迁移 `20260917_0004`：`screening_entry_status` 枚举 + `screening_entry`（`UNIQUE(raw_job_id)` 幂等流转）。
2. Capture/Screening repo：`create_screening_entry` / `list_screening_entries` / `get_screening_entry` / `update_screening_entry_status`；`list_shortlist()` 排除已流转岗位。
3. enrich worker：`done` 分支写入筛选池（旁路、失败不拖垮队列）。
4. REST：`GET /screening-entries` 与 `promote` / `dismiss` / `revert`；`enrich_state` 去掉 `paused`。
5. 控制台：`/screening` 三栏页（A4 案卷 + 评估占位 + 人工决策）、`/shortlist` 候选最小列表、`/jobs` 去掉导入面板、`/capture` 承接导入。
6. 测试：pytest（状态推导、流转、端点、契约）+ vitest（路由、颜色契约）。

## 非范围

- Filter Set / Stage-0 规则引擎 / `screen_result` 淘汰与捞回；JD 画像解析；真实 LLM 评分与 Prompt（右栏为占位）。
- 投递包、三形态简历、招呼语、聊天回采、扩展侧改动。
- 自动推进候选区或任何自动调权/自动应用策略。
