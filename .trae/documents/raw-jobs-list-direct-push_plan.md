# 列表直传接入：主系统实现 POST /api/v1/raw-jobs 实施计划

```yaml
task: 接入 boss-helper 扩展「翻页列表直传」——主系统新增 POST /api/v1/raw-jobs 批量幂等入库
domain_owner: Capture 采集域（被动入库），无跨域写库
architecture_refs: [ARCH-API-001, ARCH-CONTRACT-001, ARCH-REL-001, ARCH-EXT-001, ARCH-DATA-001, ARCH-SEC-001, ARCH-GOV-002, ARCH-OBS-001]
contracts:
  - contracts/api/openapi.yaml（新增 POST /raw-jobs 与请求/响应 schema）
  - contracts/ws/raw-job.schema.json（复用，不改：jobs 数组每项即该合同载荷）
red_lines:
  - 纯被动入库：禁止下发任何 WS 命令、禁止触发三档链、无自动动作（ARCH-GOV-002）
  - loopback + 配对 token 鉴权复用现有 require_local_auth（127.0.0.1 / Bearer / Origin）
  - list_json 仅存本机，与既有 job.captured / 导入路径同级；无聊天字段，不引入新 PII 类别
  - 外部仓库 E:\GitHub\boss-helper-main 只读，本任务零改动插件
```

## 一、Repository Research（调研结论）

### 1. 插件侧契约（已只读核实，不修改）

- 触发链：用户手动翻页 → MAIN world 800ms URL diff → content script 中继 → SW `onPageTurned`（[background.ts#L491-L519](file:///E:/GitHub/boss-helper-main/boss-helper-main/src/entrypoints/background.ts#L491-L519)）。四闸门：开关+令牌、三档链忙时让路、同 URL 5 分钟防抖、空数据不发。
- HTTP 调用：[restUploadRawJobs](file:///E:/GitHub/boss-helper-main/boss-helper-main/src/bridge/ws-client.ts#L350-L375)
  - `POST http://127.0.0.1:8000/api/v1/raw-jobs`（默认 apiBase `http://127.0.0.1:8000`，与主系统 API_PORT 8000 对齐）
  - Header：`Content-Type: application/json` + `Authorization: Bearer {pairingToken}`
  - Body：`{ "source": "boss", "tier": "list", "jobs": [...] }`
- jobs 每项由 [mapListJob](file:///E:/GitHub/boss-helper-main/boss-helper-main/src/bridge/raw-job-mapper.ts#L24-L53) 产出，字段集合 = `contracts/ws/raw-job.schema.json` 的 list 档载荷：
  `source, ext_id, tier, title, company, city?, district?, salary_text?, exp_text?, degree?, list_tags?, boss_name?, list_url, list_json(整条 Vue 原始对象), captured_at(ISO)`；直传不设 batch_id；title/company 可能为空串（服务端须拒绝该条）。
- 插件对响应只看 `res.ok`，失败仅 `console.warn`，不重试、不弹窗。服务端不需要为兼容它做特殊响应形状，但应返回计数便于排障。

### 2. 主系统现状（本仓库）

- 路由都挂在 [main.py](file:///e:/GitHub/AI_Resume_OS/services/api/app/main.py#L194-L195) 同一个 `prefix=/api/v1` router 上，统一 `Depends(require_local_auth)`：loopback 对等体（容器模式放宽到私网）+ Origin 白名单（含 `chrome-extension://`，[main.py#L111-L125](file:///e:/GitHub/AI_Resume_OS/services/api/app/main.py#L111-L125)）+ Bearer 配对 token。POST 复用即可，无需新鉴权代码。
- 入库内核已存在：[capture_repo.upsert_raw_job](file:///e:/GitHub/AI_Resume_OS/services/api/app/capture_repo.py#L127-L259)，按 `(source_id, ext_id)` upsert，list/detail 合并、`list_json` 首次值保留（COALESCE）、薪资/经验/学历在服务端清洗、返回是否新插入。天然幂等。
- 载荷模型已存在：[RawJobPayload](file:///e:/GitHub/AI_Resume_OS/services/api/app/event_models.py#L30-L70)（`extra=forbid`，list 档强制 title+company 非空）。
- 最佳同构先例：[job_import.run_import](file:///e:/GitHub/AI_Resume_OS/services/api/app/job_import.py#L119-L144)——逐条映射/校验→建一个 list 档溯源 batch_run→循环 upsert→complete_batch→返回 `{batch_id,total,created,merged,invalid}`；无效条按 index 报告、不中断整批。
- DDL：[0001 迁移](file:///e:/GitHub/AI_Resume_OS/migrations/versions/20260916_0001_capture_foundation.py#L80) 中 `batch_run.trigger` 是自由 Text（无 CHECK），既有先例值 `console-import`。**本任务零 DDL、零迁移**。
- 契约测试 [test_contracts.py](file:///e:/GitHub/AI_Resume_OS/tests/contract/test_contracts.py#L40-L58) 只要求路径集合包含既有路径并冻结版本/loopback 声明；向 `/raw-jobs` 增加 POST operation 不破坏。
- 错误信封、422 校验处理器、trace_id 均为现成机制。
- `docs/api/*.md` 是接口响应样本（URL+JSON），非散文文档；REST 机器真源是 openapi.yaml（docs/13 的路径表为 v1.0 设想版，与实现路径不同，不改动以免双份漂移）。

## 二、方案要点

1. **新模块** `services/api/app/raw_jobs_push.py`：解析直传信封 + 逐条校验 + 复用 `upsert_raw_job` 入库。
2. 每次 POST 建一个 **溯源 batch_run**（`kind="list"`, `trigger="extension-list-push"`），同步 `completed`。它不对应任何采集动作、不产生 WS 命令——与插件「不登记采集批次」不冲突：不登记指不调 `/captures`、主系统不回发 `capture_list`；服务端内部留溯源行是 job_import 已确立的先例。
3. **信封级**（整体 422）：`source≠"boss"`、`tier≠"list"`、`jobs` 非数组/空/超 100 条、多余字段。
4. **条目级**（计入 `invalid`，不中断）：非对象、`RawJobPayload` 校验失败（含 title/company 空串、未知字段）、条目 `source/tier` 与信封不一致。有效条强制盖本次溯源 `batch_id` 后入库。
5. 响应 `200`：`{batch_id, total, created, merged, invalid:[{index,reason}...]}`（invalid 最多回 50 条，同导入先例）。
6. 幂等：重发同页 → 全部 `merged`、行数不变、`list_json` 保留首次值；无 Idempotency-Key 需求（插件不发，upsert 即幂等）。

## 三、Files and Modules（改动清单）

- `contracts/api/openapi.yaml`（契约先行）
  - components.schemas 新增 `RawJobsUpload`（extra forbid：source const boss、tier const list、jobs 1..100 的 RawJobUploadItem 数组；item schema 复用 raw-job.schema.json 字段集，list 档 required title/company）与 `RawJobsUploadResult`（同 JobImportResult 形状）。
  - `/raw-jobs` 下新增 `post`（tag capture，summary 注明「扩展翻页直传；被动幂等入库，不触发采集命令」，responses 200/401/403/422）。
- `services/api/app/raw_jobs_push.py`（新建，小模块）
  - `MAX_JOBS = 100`、`PUSH_TRIGGER = "extension-list-push"`
  - `class RawJobsUploadError(ValueError)`（信封级错误）
  - `parse_upload(body, *, batch_id) -> (list[RawJobPayload], list[dict])`
  - `async run_push(body) -> dict`：建 batch → 校验 → 逐条 upsert 计数 → complete_batch → 返回结果；一条结构化 info 日志（仅计数/ext_id 数量，不打内容）。
- `services/api/app/main.py`
  - 新增 `RawJobsUpload` Pydantic 请求模型（`extra="forbid"`，jobs 用 `Field(min_length=1, max_length=100)`）。
  - 在 capture router 注册 `POST /raw-jobs`（200），调用 `raw_jobs_push.run_push`，信封错误映射 422 `PAYLOAD_INVALID`。与 GET 同路径不冲突（方法不同）。
- `tests/capture/test_raw_jobs_push.py`（新建）
  - 纯单测（无需 DB）：正常映射（batch_id 注入、字段透传、list_json 保留）；各类无效条按 index 报告且有效条不丢；信封 source/tier 不一致拒绝；上限常量。
  - `RUN_DB_TESTS` 门控的集成测试：连推两次幂等（created→merged、行数不变、list_json 首值保留、薪资服务端解析）；batch_run 留痕 `(list, extension-list-push, completed)`。沿用 test_job_import.py 的 TRUNCATE/门控写法。
- `tests/capture/test_capture_api.py`（扩展）
  - FakeRepo 加 `upsert_raw_job`（记录调用，按 ext_id 模拟 created/merged）。
  - POST 200 用例：响应计数、create/complete batch 被调用、**`fake_registry.commands == []`（红线证明：直传绝不下发命令）**。
  - 422 用例：空 jobs、错误 tier/source、多余字段、101 条。
  - 401/403 已由同依赖既有测试覆盖，不重复。

## 四、Implementation Steps（顺序）

1. 改 `contracts/api/openapi.yaml`（schema + path operation）。
2. 新建 `services/api/app/raw_jobs_push.py`（解析 + run_push）。
3. 改 `main.py` 挂 POST 路由与请求模型。
4. 新建/扩充测试（单测 → API 路由测试 → DB 门控测试）。
5. 本地验证（见下），全部通过后按 DoD 自评。
6. 若 compose 栈在运行，重建 api 服务使接口生效（不触碰 worker/web/插件）。

## 五、Dependencies and Considerations

- 无新依赖、无 DDL/迁移、无 codegen 产物（packages/contracts-py|ts 不由 openapi 生成，仓库无该流水线）。
- 与 `/jobs/import` 的差异：导入吃「扩展导出器 JSON」（jobId/company/raw 嵌套），直传吃「已归一化的合同载荷」，故独立模块，不塞进 job_import。
- 插件 mapper 透传的 `list_json` 是 Vue 原始卡片对象（可能含数十字段），与 WS job.captured 入库口径完全一致，不引入新数据类别；不写任何聊天/证据字段。
- 服务端对 `captured_at` 缺失/畸形：pydantic 解析失败 → 该条 invalid（插件总会带 ISO 值）。
- 不使用 Idempotency-Key：幂等键即 `(source, ext_id)` upsert，重放安全。
- 溯源 batch 每次 POST 一行（活跃翻页约 5 分钟一行），量级可忽略；open-API 中 BatchRun.trigger 枚举（console/extension/manual）是摘要 schema，DB 为自由文本（console-import 已是先例），本次不扩 openapi 枚举以免影响冻结契约，在代码注释说明。

## 六、Validation

- `python -m pytest tests/capture/test_raw_jobs_push.py tests/capture/test_capture_api.py tests/contract -q` 全绿。
- `python -m pytest -q`（非 DB 全量）全绿。
- DB 集成（如环境可用）：`docker compose run --rm -e RUN_DB_TESTS=1 api python -m pytest tests/capture -q`。
- 红线负向断言：直传 POST 后 registry 零命令（API 测试）；非 loopback 403 / 无 token 401（依赖既有测试）。
- 契约：openapi YAML 可被 yaml.safe_load 解析，既有契约测试通过。
- 接口实测（服务重建后）：带 Bearer `curl -X POST .../api/v1/raw-jobs` 一份合成信封，确认 200 与计数；重复一次确认 merged；随后 GET /raw-jobs 可见该岗位。

## 七、Risks

- **插件实际载荷与合同漂移**（如多出未知字段）：`extra=forbid` 会把该条记为 invalid 而非全批失败，可在响应 invalid 中定位；不放宽合同。
- **直传与三档链同时到达产生合并竞争**：两者都走同一 upsert（单连接、ON CONFLICT 单语句），合并规则已覆盖 list→detail；直传在插件侧还有「忙时让路」闸门，风险低。
- **溯源 batch 量增长**：仅审计行、体积小；不做清理逻辑（超出本任务范围）。
- **容器重建影响在跑的服务**：仅重建 api；Postgres 数据卷不动；重建不影响配对 token（卷持久化）。
