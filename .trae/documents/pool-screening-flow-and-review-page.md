# 计划：岗位池→筛选池自动流转 + 筛选池三栏评估页 + 导入面板归位

```yaml
task: P1-005-pool-screening-flow
status: draft_for_human_review
domain_owner: Screening / Capture / Console
architecture_refs:
  - ARCH-SCREEN-001   # Stage-0 纯规则、零 LLM、可解释、可捞回
  - ARCH-MATCH-001    # Fit/Gap/Risk 输出；改权重须人工批准
  - ARCH-GOV-002      # 进入候选区必须人工确认；系统不得自动应用策略
  - ARCH-RETRO-001    # 漏斗口径 captured → screened_pass → shortlisted
contracts:
  - contracts/api/openapi.yaml
  - migrations/versions/20260916_0004_screening_entry.py
data_classification: internal
human_approval: required   # DDL/迁移、契约、页面地图（01 篇）、DESIGN.md、新增错误码
nfr:
  - 流转为内部状态迁移，不产生任何对外动作
  - 进入候选区只由人工点击触发（ARCH-GOV-002）
  - 岗位池列表与重启重建均排除已流转岗位（无重复流转环路）
  - 所有新增 UI 仅使用 :root[data-theme] token，无颜色字面量
red_lines:
  - AGENTS.md §绝对禁止 1（自动对外动作）、6（无证据 Claim / 不虚构）、8（禁止自动调权/自动应用策略）
  - AGENTS.md §必须遵守（契约先行、每新行为带测试）
  - 不改 ADR、AGENTS.md、24 篇红线、验收阈值；不弱化既有测试（routes 断言属页面地图同步更新，随本计划人审）
```

---

## 1. Summary（四个问题的结论）

| # | 你的要求 | 结论 |
|---|---|---|
| 1 | 补全已暂停时，岗位状态不要显示「已暂停」 | 后端不再把全局队列暂停投影到单个岗位状态；`enrich_state` 只按数据推导。队列级暂停仍由顶部「补全已暂停」条表达（那是队列状态，不是岗位状态）。 |
| 2 | 岗位池与筛选池分离；补全完成自动进筛选池并从岗位池消失 | 新增 `screening_entry` 表落流转记录；enrich worker 判定 `done` 时自动写入（幂等）；岗位池列表与重启重建都排除已流转岗位。 |
| 3 | 筛选池三栏：左列表 + 中 A4 案卷 + 右评分建议，可点进候选区 | 新增 `/screening` 一级导航（流程第 3 级），三栏布局 + A4 比例案卷（复用现有 job-profile 数据与渲染）；右栏本期为**评分占位**（待评分 + 禁用按钮 + 明确"未接入"说明），主操作「进入候选区」（人工确认）、次操作「忽略」；`/shortlist` 候选区做最小列表 + 可退回筛选池。 |
| 4 | 导入扩展导出的岗位列表归采集中心 | `ImportPanel` 从 `pages_jobs.tsx` 迁到 `App.tsx` 的 `CapturePage`；岗位列表表格（浏览筛选、加入岗位池、详情面板）留在岗位池页。 |

---

## 2. 现状分析（已核对）

- 页面/路由：[routes.ts](file:///e:/GitHub/AI_Resume_OS/apps/web/src/routes.ts#L17-L28) 共 10 条，`flowRoutes` 7 条（`/`、`/capture`、`/jobs`、`/shortlist`、`/packages`、`/events`、`/retrospective`）；页面组件映射在 [App.tsx](file:///e:/GitHub/AI_Resume_OS/apps/web/src/App.tsx#L379-L389)。**不存在筛选池页面**，`/shortlist`（候选区）只渲染 `EmptyState`。
- `ImportPanel` 在 [pages_jobs.tsx](file:///e:/GitHub/AI_Resume_OS/apps/web/src/pages_jobs.tsx#L94-L160)，由 `JobsPage` 首行渲染；采集中心 `CapturePage` 内联在 [App.tsx](file:///e:/GitHub/AI_Resume_OS/apps/web/src/App.tsx#L121-L299)。
- 暂停污染岗位状态：[main.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/main.py#L291-L317) `_shortlist_item` 里 `elif enrich.is_paused(): state = "paused"`，而 `is_paused()` 是全局队列标志（[enrich.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/enrich.py#L69-L70)）。
- enrich 完成点：[enrich.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/enrich.py#L268-L276) `outcome == "done"` 分支（`_enrich_one` 三处返回 done：无公司导航 / 公司已采 / 公司页落地）；重启重建在 `_rebuild()`（[enrich.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/enrich.py#L232-L237)），它遍历 `capture_repo.list_shortlist()`。
- 岗位池数据：[shortlist](file:///e:/GitHub/AI_Resume_OS/migrations/versions/20260916_0003_shortlist.py#L29-L74) 表（`shortlist_status = confirmed|removed`，部分唯一索引 `uq_shortlist_confirmed_raw_job`），当前实现见 [capture_repo.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/capture_repo.py#L555-L570)。
- 筛选域现状：`filter_set` / `screen_result` 只在骨架契约，**零代码**；Stage-0 被设计为「零 LLM 纯规则」，AI 打分仅为可选附加且「永不覆盖 verdict」（ARCH-SCREEN-001）。
- 视觉约束：[styles.contract.test.mjs](file:///e:/GitHub/AI_Resume_OS/apps/web/src/styles.contract.test.mjs#L9-L19) 只允许 `var(--token)`（扫描 3 个文件，本期扩到新文件）；`DESIGN.md` 为视觉真源（三主题、形状先于颜色、AI 内容须标注草稿态、评分禁用红绿）。
- 迁移入口：仅 Alembic，`python -m alembic upgrade head`（[migrations/README.md](file:///e:/GitHub/AI_Resume_OS/migrations/README.md#L6-L13)），API 启动不自动迁移。

---

## 3. 改动清单（决策完整，可直接执行）

### 3.1 契约（先改契约再实现）

**`contracts/api/openapi.yaml`**
1. `Error.code` 枚举新增两码：`SCREENING_ENTRY_NOT_FOUND`（404）、`SCREENING_TRANSITION_INVALID`（409）。
2. `ShortlistItem.enrich_state` 枚举由 `[pending, detail_done, done, failed, paused]` 改为 `[pending, detail_done, done, failed]`，description 补一句「队列暂停不投影到岗位状态；暂停只在 `/enrich/queue` 表达」。
3. 新增 schema `ScreeningEntryItem`：

```yaml
    ScreeningEntryItem:
      type: object
      required: [id, raw_job_id, ext_id, status, entered_at]
      properties:
        id: { type: string, format: uuid }
        raw_job_id: { type: string, format: uuid }
        ext_id: { type: string }
        title: { type: [string, 'null'] }
        company: { type: [string, 'null'] }
        city: { type: [string, 'null'] }
        salary_text: { type: [string, 'null'] }
        status: { type: string, enum: [screened, candidate, dismissed] }
        entered_at: { type: string, format: date-time }
```

4. 新增 4 个 path（tags: `[screening]`）：

```yaml
  /screening-entries:
    get:      # status=screened(默认)|candidate + limit/offset → {items, limit, offset}
  /screening-entries/{id}/promote:   # screened → candidate（人工确认进入候选区）
  /screening-entries/{id}/dismiss:   # screened → dismissed（终态，不进候选区）
  /screening-entries/{id}/revert:    # candidate → screened（候选区退回筛选池）
```
每个写操作响应：`200 ScreeningEntryItem` / `404 SCREENING_ENTRY_NOT_FOUND` / `409 SCREENING_TRANSITION_INVALID`。

### 3.2 数据库迁移（🟡 人审）

**新增 `migrations/versions/20260916_0004_screening_entry.py`**（`revision="20260916_0004"`，`down_revision="20260916_0003"`，`downgrade` 抛 `RuntimeError("JobOS migrations are forward-only")`）：

- `CREATE TYPE screening_entry_status AS ENUM ('screened','candidate','dismissed')`
- `screening_entry`：
  - `id uuid PK default gen_random_uuid()`
  - `raw_job_id uuid NOT NULL REFERENCES raw_job(id)`
  - `status screening_entry_status NOT NULL default 'screened'`
  - `assessment_json jsonb NULL` —— 本期**始终为空**，作为评分引擎（Prompt/权重经人审后）的快照槽
  - `entered_at timestamptz NOT NULL default now()`、`updated_at timestamptz NOT NULL default now()`
  - `CONSTRAINT uq_screening_entry_raw_job UNIQUE (raw_job_id)`（一个岗位只流转一次；`dismissed` 也不回岗位池，避免自动重流转环路）
  - 索引 `ix_screening_entry_status_entered (status, entered_at DESC)`
- **不改** `contracts/db/0001_baseline.skeleton.sql`：骨架是 v1.0 既有基线，本对象为本期新增，只存在于迁移中。

### 3.3 后端

**`services/api/app/capture_repo.py`**
- 新增 `create_screening_entry(raw_job_id: UUID) -> bool`：`INSERT ... ON CONFLICT (raw_job_id) DO NOTHING RETURNING id`（幂等）。
- 新增 `list_screening_entries(*, status: str = "screened", limit: int = 50, offset: int = 0) -> list[dict]`：JOIN `raw_job`，返回 `id/raw_job_id/ext_id/title/company/city/salary_text/status/entered_at`，按 `entered_at DESC`。
- 新增 `get_screening_entry(entry_id: UUID) -> dict | None`。
- 新增 `update_screening_entry_status(entry_id: UUID, *, to_status: str) -> dict | None`：合法迁移 `screened→{candidate,dismissed}`、`candidate→screened`；非法抛 `ScreeningTransitionInvalid`；不存在返回 `None`；更新 `updated_at`。
- 修改 `list_shortlist()`（[capture_repo.py:555](file:///e:/GitHub/AI_Resume_OS/services/api/app/capture_repo.py#L555-L570)）SQL 追加：

```sql
   AND NOT EXISTS (
       SELECT 1 FROM screening_entry se WHERE se.raw_job_id = sl.raw_job_id
   )
```
效果：岗位池列表不再出现已流转岗位；`enrich._rebuild()` 因为复用该函数，重启也自动跳过已流转岗位。
- `add_to_shortlist()` 不动：`uq_shortlist_confirmed_raw_job` 仍挡住重复入池，流转不清除 `shortlist` 行。

**`services/api/app/enrich.py`**
- `_worker_loop` 的 `if outcome == "done":` 分支（[enrich.py:268](file:///e:/GitHub/AI_Resume_OS/services/api/app/enrich.py#L268-L270)）新增自动流转：

```python
if outcome == "done":
    try:
        await capture_repo.create_screening_entry(raw_job_id)
    except Exception:  # noqa: BLE001 - 流转失败不得拖垮 worker
        logger.exception("screening entry write failed")
    _queued.discard(raw_job_id)
    _failed.pop(raw_job_id, None)
```
- `_rebuild()` 注释更新为「已流转岗位不在 `list_shortlist()` 结果里，不会被重复入队」。

**`services/api/app/main.py`**
- 把状态推导抽成模块级纯函数（便于测试，且彻底去掉暂停投影）：

```python
def derive_enrich_state(
    *, failed_reason: str | None, detail_at: Any, jd_text: str | None,
    ext_company_id: str | None, company_ids: set[str],
) -> str:
    if failed_reason is not None:
        return "failed"
    if detail_at is None or not jd_text:
        return "pending"
    return "done" if (ext_company_id is None or ext_company_id in company_ids) else "detail_done"
```
  `_shortlist_item` 改为调用它（删除 `elif enrich.is_paused(): state = "paused"`）。
- 新增 4 个端点（`/api/v1` 前缀、沿用 `require_local_auth`）：

```python
@router.get("/screening-entries", tags=["screening"])
async def read_screening_entries(status: Literal["screened", "candidate"] = "screened",
                                 limit: int = 50, offset: int = 0) -> dict[str, Any]
# 404 → ApiProblem(404, "SCREENING_ENTRY_NOT_FOUND", ...)
# 非法迁移 → ApiProblem(409, "SCREENING_TRANSITION_INVALID", ...)
@router.post("/screening-entries/{entry_id}/promote", tags=["screening"])   # screened → candidate
@router.post("/screening-entries/{entry_id}/dismiss", tags=["screening"])   # screened → dismissed
@router.post("/screening-entries/{entry_id}/revert", tags=["screening"])    # candidate → screened
```

### 3.4 前端

**`apps/web/src/lib/capture.ts`**
- `EnrichState` 去掉 `'paused'`。
- 新增 `ScreeningEntryStatus`（`'screened' | 'candidate' | 'dismissed'`）、`ScreeningEntryItem`（与契约同形）、`fetchScreeningEntries(status, signal?)`、`promoteScreeningEntry(id)`、`dismissScreeningEntry(id)`、`revertScreeningEntry(id)`（`parseError` 复用）。

**新增 `apps/web/src/job-profile-view.tsx`**（共享视图，供抽屉与 A4 案卷复用）
- 从 `pages_jobs.tsx` 抽出 `COMPANY_SECTION_LABEL`、`sectionText`、`CompanySections`，以及「事实表 + 技能标签 + JD 全文块 + 公司画像块」的渲染。
- 导出 `JobProfileView({ job, company })`；宿主各自提供容器与标题（副标题里的「DETAIL · 本机数据」等留在宿主）。
- 无颜色字面量（沿用 `var(--token)` 类名 `.detail-facts/.detail-tags/.jd-text/.detail-sections/.detail-text`）。

**新增 `apps/web/src/pages_screening.tsx`**
- `ScreeningPage`：
  - 数据：`useQuery(['screening-entries','screened'], fetchScreeningEntries, refetchInterval: 6000)`；选中条目 → `useQuery(['job-profile', extId], fetchJobProfile)`（复用既有端点）。
  - 布局 `.screening-split` 三栏：
    - 左 `.screening-list`：条目按钮（第 1 行职位、第 2 行 `公司 · 薪资 · 进入时间`），选中态 `.selected`；空态「筛选池为空：岗位池补全完成的岗位会自动流入这里。」
    - 中 `.screening-stage` → `.a4-sheet`（A4 比例，内部滚动）内放 `JobProfileView`；顶部一行案卷抬头（`mono-label` + 职位 + `ext_id` 等宽小字）。
    - 右 `.screening-assess`：`待评分` 占位块（`○ 待评分` + 说明「评分引擎未接入：Prompt 与权重需人审后另行实现」，`assessment_json` 本期为空）+ 禁用按钮「生成评估」+ 主操作「进入候选区」（`promoteScreeningEntry`）+ 次操作「忽略」（首次点击变为「确认忽略」，`dismissScreeningEntry`）。
  - 动作成功后 `invalidateQueries(['screening-entries'])`；失败显示错误信息。
- `CandidatesPage`（`/shortlist`）：`useQuery(['screening-entries','candidate'], ...)` 最小列表（职位/公司/薪资/进入时间）+「退回筛选池」（`revertScreeningEntry`）；空态自渲染（复用 `.empty-state` 结构 + 「前往筛选池」链接）。

**`apps/web/src/pages_jobs.tsx`**
- 删除 `ImportPanel` 组件与 `importJobs` / `JobImportResult` 引用；`JobsPage` 去掉 `<ImportPanel />`。
- `JobDetailPanel` 改用 `JobProfileView`（抽屉外壳、标题、`EnrichBadge`、`failure_reason` 提示保留）。
- `ENRICH_LABEL` / `EnrichBadge` 去掉 `paused`。
- `PoolPanel` 空态文案：「岗位池为空。补全完成的岗位会自动流入筛选池，可在筛选池逐条判断。」

**`apps/web/src/App.tsx`**
- 迁移 `ImportPanel` 进来（需新增 `useQueryClient`、`useRef`、`importJobs`、`JobImportResult` 引用），渲染在 `CapturePage` 的 `.capture-body` 内、`.capture-actions` 之前（与「最近入池岗位 / 公司画像」同区）。
- 路由渲染新增：`/screening → <ScreeningPage />`、`/shortlist → <CandidatesPage />`；`EmptyState` 渲染条件排除 `/shortlist`（该页自渲染空态）。
- `.page-grid` 在 `/screening` 时加 `no-context-rail` 类（该页自身右栏承担第二视角，避免四栏挤压）。

**`apps/web/src/routes.ts`**
- 在 `/jobs` 与 `/shortlist` 之间插入：

```ts
{ path: '/screening', label: '筛选池', shortLabel: '筛选', eyebrow: 'Screening pool', title: '筛选池',
  description: '补全完成的岗位自动流入；逐条对照 JD 与公司画像，人工决定是否进入候选区。', group: 'flow' },
```
- `/jobs` 改为 `label: '岗位池'`、`shortLabel: '岗位'`、`title: '岗位池'`，description 说明「浏览已导入岗位并人工入池；补全完成的岗位自动流向筛选池」。
- `/shortlist` 去掉 `emptyTitle/emptyDescription/nextPath/nextLabel`（改由 `CandidatesPage` 自渲染），`title/description` 保留。

**`apps/web/src/styles.css`**
- 新增：`.page-grid.no-context-rail`（单栏）、`.screening-split`（≥1280 三栏 `minmax(240px,290px) minmax(0,1fr) minmax(240px,300px)`；≤1279 收窄；≤1023 单列堆叠）、`.screening-list`（条目按钮 + `.selected` 用 `--accent-soft`）、`.a4-sheet`（`aspect-ratio: 210 / 297; max-width: 480px; margin-inline: auto; padding: 24px; border: 1px solid var(--hairline); background: var(--sheet); overflow: auto;`）、`.screening-assess` / `.assess-placeholder`（`--canvas-inset` 底 + `○` 符号 + 说明文案）。
- 删除 `.enrich-badge.paused`。全部仅用 token。

### 3.5 文档（🟡 人审）

- **`docs/architecture/01-系统设计文档.md`** 页面地图：把 `POOL[岗位池与筛选]` 拆为 `POOL[岗位池]`（Raw Job 列表 / 人工入池 / 补全队列）与 `SCR[筛选池]`（A4 案卷视图 / 评估（占位）/ 进入候选区），并在原则行补一句流转口径：「补全完成自动流入筛选池；进入候选区仍必须人工确认（ARCH-GOV-002）」。
- **`DESIGN.md`** 新增小节「筛选池三栏与 A4 案卷」：栅格与断点、A4 比例约束、评估区本期为占位且必须显式标注「未接入」、评分相关展示禁用红绿（用 `--ink/--hold/--evidence` + `●○`）。
- **新增 `docs/delivery/tasks/P1-005-pool-screening-flow.md`**：按 [P1-004](file:///e:/GitHub/AI_Resume_OS/docs/delivery/tasks/P1-004-capture-foundation.md#L1-L43) 的任务头格式（task/status/domain_owner/architecture_refs/contracts/data_classification/human_approval/nfr/acceptance_tests/red_lines）+ 目标 / DoR 审计 / 范围 / 非范围。

### 3.6 测试（每个新行为都带测试）

- **`tests/capture/test_capture_api.py`**
  - FakeRepo 扩展 `list_screening_entries/get_screening_entry/update_screening_entry_status`，新增用例：默认列表为 screened；`promote` 后可从 `status=candidate` 查到；`dismiss`/`revert`；非法迁移 → 409 + `SCREENING_TRANSITION_INVALID`；未知 id → 404 + `SCREENING_ENTRY_NOT_FOUND`。
- **`tests/capture/test_enrich_queue.py`**
  - FakeRepo 增加 `create_screening_entry` 记录并用例断言：`outcome == done` 时写入一次；重复完成不重复写（幂等由 `ON CONFLICT` 保证，fake 里按 raw_job_id 去重）；`create_screening_entry` 抛错时 worker 不崩且该条目仍出队。
- **新增 `tests/capture/test_enrich_state.py`**（纯函数，无需 DB）
  - `derive_enrich_state` 四分支；`monkeypatch enrich._paused = True` 时结果不变（**需求 1 的回归锚点**）。
- **新增 `tests/capture/test_screening_repo.py`**（`RUN_DB_TESTS` 门控，默认跳过）
  - `create_screening_entry` 幂等；`list_shortlist()` 排除已流转岗位；`update_screening_entry_status` 合法/非法迁移。**注意：不要在本机业务库上跑 `RUN_DB_TESTS`（会 TRUNCATE）。**
- **`tests/contract/test_contracts.py`**：capture REST 断言集合加入 `/screening-entries`；断言 `Error.code` 含两个新码、`ShortlistItem.enrich_state` 不含 `paused`；断言 `ALLOWED_COMMANDS` 未新增任何对外动作命令。
- **vitest**：`routes.test.ts` 路径列表 + `/screening`、`flowRoutes` 7 → 8（用例名同步改为「funnel」并注明页面地图变更随 P1-005 人审）；`styles.contract.test.mjs` 扫描范围扩到 `pages_screening.tsx`、`job-profile-view.tsx`。

---

## 4. 关键决策与假设

1. **流转条件** = 岗位达到 `enrich_state == "done"`（`jd_text` 存在，且公司快照已入库或该导出根本没有公司导航）；无公司导航的岗位照常流转（与现有 `done` 定义一致）。
2. **流转不删岗位池数据**：`shortlist` 行保持 `confirmed`，岗位池列表用 `NOT EXISTS screening_entry` 排除；`dismissed` 也不回岗位池（`UNIQUE(raw_job_id)` + `ON CONFLICT DO NOTHING`，杜绝自动重流转环路）。
3. **流转时机**：worker 判定 done 的同一轮内写入；补全失败（`failed`）与暂停中的队列不动。重启时 `_rebuild()` 会把「已完成但尚未流转」的岗位补上（现有数据即属此种，部署后会自动补流转）。
4. **候选区回退**只有 `candidate → screened` 一种；`dismissed` 为终态。
5. **AI 评分本期占位**：不调用任何模型、不写 `assessment_json`、不做任何权重；右栏必须显式写「未接入」，不得伪装成已评分（红线 6：禁止无证据 Claim）。
6. 不新增/修改 ADR；不新增 ARCH 条目（引用上表三条）；若你认为需要独立 ARCH 条目，另开一条人审项。
7. 页面地图由 7 级变 8 级属 🟡（导航即漏斗签名变更），随本计划一并人审；`routes.test.ts` 的同步更新属页面地图变更，非弱化测试。

**非范围**：Filter Set / Stage-0 规则引擎 / `screen_result` 淘汰与捞回、JD 画像解析（ARCH-MATCH-001）、真实 LLM 评分与 Prompt、投递包与招呼语、聊天相关内容、扩展侧任何改动。

---

## 5. 验证步骤

1. 静态与单测：`pnpm --filter @jobos/web typecheck`、`pnpm --filter @jobos/web test`、`pnpm --filter @jobos/web build`。
2. 非 DB pytest（一次性容器，不要带 `RUN_DB_TESTS`）：
   `docker compose run --rm -e CONTAINER_MODE=false -e PYTHONDONTWRITEBYTECODE=1 -v E:\GitHub\AI_Resume_OS:/workspace -w /workspace --entrypoint bash api -c 'pip install -q pytest jsonschema httpx && python -m pytest -p no:cacheprovider -q'`
3. 迁移：`docker compose run --rm api python -m alembic upgrade head`，随后 `\d screening_entry` 与 `select unnest(enum_range(NULL::screening_entry_status));` 核对。
4. 重建服务：`docker compose build api web` → `docker compose up -d api web`。
5. 数据核对（部署后自动补流转现有 4 条已补全岗位）：
   - `select count(*) from screening_entry;` 期望 4 且 `status='screened'`
   - `GET /api/v1/shortlist` 期望为空数组；`GET /api/v1/screening-entries` 期望 4 条
6. 浏览器核对（http://127.0.0.1:4173）：`#/capture` 有导入面板、`#/jobs` 无导入面板且池内为空、`#/screening` 三栏 + A4 案卷 + 占位评估 + 「进入候选区」/「忽略」生效、`#/shortlist` 显示已进入候选区的岗位且可退回；切换三主题与窄屏（≤1023px）确认堆叠与 token 表现。
7. 红线回归：断言 `/screening-entries` 无任何自动推进路径（只有人工 POST），节点 `ALLOWED_COMMANDS` 未新增对外命令。