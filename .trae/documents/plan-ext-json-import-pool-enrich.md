# 计划：插件 JSON 导入 + 岗位池自动补全链路（详情页/公司页按需抓取）

> 状态：待本人批准 · 日期 2026-09-16
> 决策记录：导入=页面上传 JSON；入池后自动排队串行抓取（用户已确认）。

## 1. 概要

重构扩展↔主系统数据链路：

1. **列表数据不再抓取**：主系统新增导入端点，直接吃扩展侧导出的岗位列表 JSON（样本：`C:\Users\21598\Downloads\岗位列表-2026-09-16 (3).json`，`{pageUrl, jobs[15]}`），落 `raw_job`（tier=list），Web `/jobs` 页展示+筛选。
2. **岗位池**：筛选后手动「加入岗位池」→ 写 `shortlist`（confirmed）。
3. **按需补全**：入池即自动入队，主系统经 WS 串行驱动扩展逐个打开**详情页**（复用既有 `capture_details`）→**公司页**（新增 `capture_company` 命令），数据回传 `job.updated`(detail) / `company.updated`，按既有 `(source, ext_id)` 幂等合并。节流 1800ms±20%、并发 1、风控即暂停，全部沿用红线。

## 2. 现状事实（已探明，含依据）

| 层 | 现状 | 关键文件 |
|---|---|---|
| 契约 | 7 命令已定义（`capture_details` 可复用）；`capture.phase` 枚举已预留 `"company"`；`company.updated` 事件在 `event_models.py` 有模型 | `contracts/ws/commands.schema.json`、`services/api/app/event_models.py#L134` |
| API | capture 路由+本地鉴权+`registry.send_command` 白名单（`ALLOWED_COMMANDS` frozenset）；`raw_job` upsert 幂等键 `(source_id, ext_id)`，list/detail 双层合并；`raw_company` upsert；`shortlist` 表仅需 raw_job_id | `services/api/app/main.py`、`capture_repo.py`、`registry.py#L18`、`contracts/db/0001_baseline.skeleton.sql#L161` |
| 扩展 | **仅配对握手**，无命令分发/节流/content script | `apps/extension/src/service-worker.ts`、`protocol.ts` |
| Web | hash 路由含 `/jobs` 空态页；三主题已实现；react-query 已用 | `apps/web/src/App.tsx`、`routes.ts`、`theme.ts`、`lib/capture.ts` |
| 清洗 | 服务端解析 salary/exp/degree；`200-300元/天`→`day` 已可解析 | `services/api/app/cleaning.py` |

## 3. 契约变更（先行，🟡人审）

### 3.1 `contracts/ws/commands.schema.json`
- **新增命令 `capture_company`**：payload `{ company_url: string(uri, host=zhipin.com), ext_company_id: string(min 1), delay_ms: int(≥1800) }`；加入顶层 oneOf；`additionalProperties: false`。
- **`capture_details` 增可选字段 `urls`**：`[{ext_id, url}]`——导入岗位无列表页上下文，扩展无法自拼 securityId；`urls` 优先于 `ext_ids` 拼导航（向后兼容，旧负载仍合法）。
- 保持 `auto_next_page` 恒 false 等既有约束不变。

### 3.2 `contracts/ws/events.schema.json`
- 核对/补齐 `company.updated` 事件（与 `event_models.CompanyPayload` 对齐；若已存在仅校验）。

### 3.3 `contracts/api/openapi.yaml`
- `POST /api/v1/jobs/import`（multipart，字段 `file`，.json ≤5MB，jobs ≤500）
- `POST /api/v1/shortlist`（`{ext_id, note?}`，入池即入队）
- `POST /api/v1/shortlist/{id}/remove`（status→removed）
- `GET /api/v1/shortlist`、`GET /api/v1/enrich/queue`、`POST /api/v1/enrich/resume`
- 同步重跑契约元校验（Draft 2020-12）与 `packages/contracts-*` 生成管道（禁止手改生成物）。

### 3.4 `registry.py`
- `ALLOWED_COMMANDS` += `capture_company`（白名单机制即「违禁命令注册失败」门禁）。

## 4. API 实现（services/api）

### 4.1 新文件 `app/job_import.py`（解析器）
样本 JSON → `RawJobPayload(tier="list")` 映射（`extra="forbid"` 已锁形状）：

| 导出 JSON | 目标字段 |
|---|---|
| `jobId` | `ext_id` |
| `title/company/city/district/salary/experience/degree` | 同名列（salary→`salary_text` 交服务端清洗；experience→`exp_text`） |
| `raw.jobLabels` / `raw.skills` | `list_tags` / `skill_tags` |
| `raw.brandStageName / brandIndustry / brandScaleName` | `stage` / `industry` / `scale` |
| `raw.bossName / bossTitle` | `boss_json{name,title}` + `boss_name` |
| **整条 item（含 securityId/companyUrl/gps/encryptBrandId）** | `list_json`（原样保全，可对账 + 供 enrich 导航） |
| 顶层 `pageUrl` | `list_url` |

- 校验：每条必须有 `jobId/title/company`；无效条目进 `invalid[]` 不中断整体。
- 幂等：重复导入同岗位走既有 upsert 合并（`list_json` 保留旧值不覆盖）。

### 4.2 `main.py` 新端点
- `POST /jobs/import`：创建 `batch_run(kind="import", trigger="console-import")` → 循环 `upsert_raw_job` → 返回 `{batch_id, total, created, merged, invalid}`。
- `POST /shortlist`：`add_to_shortlist()` 成功后调 `enrich_scheduler.enqueue(raw_job_id)`（返回 enriched 前的池条目）。
- `GET /shortlist`：join `raw_job`，附补全状态（`detail_at`、公司 sections 是否存在→`enrich_state: pending|detail_done|done|failed|paused`）。
- `GET /enrich/queue`、`POST /enrich/resume`。

### 4.3 新文件 `app/enrich.py`（串行补全队列）
- 进程内 asyncio 单 worker（并发恒 1）：每个任务 = `batch_run(kind="detail_company", trigger="pool-auto")` → `capture_details {urls:[{ext_id,url…}], detail_limit:1, delay_ms}`（URL 由 `list_json` 里的 jobId 拼 `https://www.zhipin.com/job_detail/<id>.html` + securityId 若有）→ 等该 batch `capture.completed`（超时 90s）→ 间隔 1800ms+20% 抖动 → `capture_company {company_url, ext_company_id}`（companyUrl/encryptBrandId 取自 `list_json`）→ 等完成。
- `capture.error{risk:true}` → 队列 `paused`，需人工 `POST /enrich/resume`；扩展离线 → 30s 退避重试。
- 重启恢复：worker 启动时扫描 `shortlist confirmed 且 (detail_at IS NULL 或 无公司数据)` 重建队列（天然幂等）。

### 4.4 `capture_repo.py` 增补
`add_to_shortlist / list_shortlist / remove_shortlist`（沿用表结构，零 DDL 变更）。

## 5. 扩展实现（apps/extension，工作量最大）

- **`src/commands.ts`（新）**：socket message 分发 `kind=command` → 按 type 路由 handler；receipt（command.started/progress/completed/error）与 event 上报封装（复用 `protocol.ts` uuid7）。
- **`src/throttle.ts`（新）**：`MIN_DELAY=1800` + ±20% 抖动；串行执行器（并发 1）；abort/risk 标志；单测锁定抖动区间。
- **`src/capture/detail.ts`、`src/capture/company.ts`（新）**：service worker 用 `chrome.tabs.create({active:false})` 打开目标页 → `chrome.scripting.executeScript` 注入提取（**被动读取 DOM/页面变量**，禁 hook 网络接口）→ 组 `job.updated(tier=detail, detail_json, jd_text…)` / `company.updated(sections, ext_company_id 从 URL 提取，与服务端下发值一致性校验)` → 关闭 tab。
  - 详情页提取：jd_text、技能标签、地址、活跃时间、薪资复核；风控/验证码页特征 → `capture.error{risk:true}`。
  - 公司页提取：公司介绍/工商信息/规模阶段行业 → `sections`。
- **manifest.json**：`host_permissions` 加 `https://www.zhipin.com/*`；`permissions` 加 `scripting`、`tabs`。
- handler：`capture_details`（按 `urls` 或 `ext_ids` 逐个）、`capture_company`、`abort`；`capture_list` 保留兼容但不被新流程调用。

## 6. Web 实现（apps/web）

- **`lib/capture.ts`**：增 `importJobs(file)`（FormData）、`fetchShortlist`、`addToPool`、`removeShortlist`、`fetchEnrichQueue`、`resumeEnrich` 及 `ShortlistItem`（含 `enrich_state`）类型。
- **新文件 `src/pages_jobs.tsx`**（App.tsx 引入，避免继续膨胀）：
  - 导入区：文件选择/拖拽 → 结果 toast（created/merged/invalid 明细）；
  - 岗位表格（沿用现有表风格与三主题 token）：关键字/城市/薪资单位/学历筛选 + 「加入岗位池」按钮（入池后行内状态「已入池 · 排队中」）；
  - 岗位池视图：池表 + 补全状态列 + 队列面板（运行中条目 / 暂停原因 / 恢复 / 中止）。
- `/capture` 页保留列表采集为备用路径，加说明「岗位列表已由 JSON 导入替代」。

## 7. 测试与验证

- **pytest**：导入解析（合成 fixture `services/api/tests/fixtures/exporter-sample.json`，脱敏合成数据，不入库真实 boss 信息）、重复导入幂等、shortlist 增删、enrich 队列串行性（mock registry，断言同时只有一个 in-flight 命令）、risk 暂停/恢复、契约负向（`capture_company` 非 zhipin.com host 拒绝、`delay_ms<1800` 拒绝、`auto_next_page` 不存在）。
- **vitest**：throttle 抖动区间与并发=1；Web 导入/入池交互。
- **手工 E2E**：compose 起服务 → 配对 → 导入样本 JSON（15 条）→ `/jobs` 展示与筛选 → 入池 1 条 → 观察：后台 tab 开详情→提取→关→≥1800ms→开公司页→提取→`GET /companies` 出现→池状态 `done`；中途断扩展验证退避；触发风控验证暂停。

## 8. 实施顺序

1. 契约（3.1–3.4）+ 元校验 + codegen
2. API：`job_import.py` → 端点 → `enrich.py` → repo 增补 + pytest
3. 扩展：throttle → commands 分发 → detail/company 提取 → manifest + vitest
4. Web：`pages_jobs.tsx` + lib + 主题三连截图走查
5. 手工 E2E 联调 → 自评清单 → **提交人工 Review（不自行合并）**

## 9. 假设与边界

- 导出 JSON 的生产者仍是现有外部工具；本项目扩展本轮**不做**「导出」按钮（可后续加在 options 页）。
- BOSS 详情/公司页 DOM 结构参考外部只读仓库经验，实现时以实际页面为准；只做被动读取。
- 队列为单进程内存态 + 启动重建，满足单机单用户定位，不引入新中间件。
- 不改 ADR/红线/验收阈值；`/capture` 列表采集链路保留不删（协议不破坏）。
