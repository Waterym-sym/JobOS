# 新建对话式案头 + 设置中心 实施计划

## 一、Repository Research（研究结论）

### 参考项目 `E:\GitHub\ai-job-os` 的布局模式
- 布局：`AppLayout`（左侧 `Sidebar` + 右侧 `Outlet`），用 `react-router-dom` v6 + `BrowserRouter`
- Sidebar 结构（从上到下）：品牌 → **「新建对话」按钮** → 主导航（找工作/简历/沟通/活动）→ 历史对话列表（flex:1 撑满）→ **底部用户区**（点击弹出菜单：设置/退出）
- 中心页 `ChatPage`：欢迎屏 + 消息流 + 输入框 + 右侧分析面板，靠 `/chat/:sessionId` 区分会话
- `LoginPage`：手机号+验证码、角色切换；`AccountSettingsPage`：资料卡 + 设置菜单列表 + 退出登录

### 当前项目 `AI_Resume_OS` 现状
- 路由：**hash 路由**（`App.tsx` 内 `useCurrentRoute` + `resolveRoute`），无 `react-router-dom`
- 布局：`.app-shell` > `.rail`（品牌 + flow nav + utility nav + 隐私声明）+ `.work-area`（topbar + page-content + context-rail）
- 已有页面：今日案头(`/`)、采集中心、岗位池、筛选池、候选区、投递包、事件确认台、复盘、模板、知识库、设置(`/settings`)
- 依赖：`react` 18、`@tanstack/react-query`；无路由库；有 `theme.ts` 主题系统

### 红线（AGENTS.md）对设计的硬约束
1. **单用户本地系统，无多租户、无云 SaaS** →「登录/注册」**只能是本机 PIN 锁屏**（首次设置本地密码、之后输入解锁），**禁止云端账号体系**
2. **禁止引入未批准框架/云组件** → 沿用现有 **hash 路由**，不引入 `react-router-dom`（非必需）
3. **禁止硬编码密钥/token/cookie；敏感值不回显** → 模型 API key、配对令牌等输入用 password 类型、从不回填明文
4. **聊天原文不出本机** → Agent 对话中心后续接 LLM 时遵守；本期只做 UI 外壳，不真实联网
5. **设置项需人审**：模型密钥、采集间隔下限、配对令牌等不可在前端被绕过——所有写入必须走后端受校验 API；本期设置页先做只读/占位 UI，后端接口留 TODO

### 设计决策
- **不引入 `react-router-dom`**，复用现有 hash 路由（`resolveRoute` 支持子路径）
- **首页从「今日案头」改为「新建对话」（Agent 对话中心）**：欢迎屏 + 快捷意图 + 输入框（本期只做外壳，不接 Agent 后端）
- **左侧栏重构**为参考项目结构：品牌 → 新建对话按钮 → 流程导航 → 历史对话（占位）→ 底部用户/设置入口
- **设置中心**：左下「设置」展开为设置组（账号/模型/本机/扩展/主题/知识库/简历/隐私），每个独立路由、独立页面（本期占位 UI + 明确字段设计）

---

## 二、功能设计（用户要求「其他的帮我设计一下有哪些功能」）

### 登录页 `/login`（本机锁屏，非云端）
- 首次使用：设置本地 PIN（6-16 位，二次确认）→ 写入 `localStorage`（仅本机）
- 已设置：输入 PIN 解锁（错误计数、可清除数据重置）
- 无邮箱/手机/云端；无注册页概念，「注册」= 首次设置本机身份（昵称 + PIN）

### 新建对话页 `/`（Agent 中心，本期 UI 外壳）
- 欢迎屏：品牌语 + 4 个快捷意图卡（智能筛选岗位 / 简历诊断 / 投递包生成 / 复盘分析）
- 输入框：多行输入 + 发送按钮（本期提交后仅显示「Agent 后端待接入」占位消息）
- 历史对话：侧栏列表（本期空态「暂无会话」）

### 设置中心（左下设置组，全部本期做占位 UI + 字段设计）
| 路由 | 页面 | 设计字段（本期只读/占位，后端留 TODO） |
|---|---|---|
| `/settings` | 账号设置 | 昵称、头像（首字占位）、本机 PIN 修改、清除本机数据、关于 |
| `/settings/model` | 模型设置 | 提供商（下拉：OpenAI 兼容/本地）、Base URL、API Key（password、不回显）、模型名、温度、最大 token |
| `/settings/local` | 本机设置 | API 端口、采集间隔下限（≥1800ms，只读）、并发（恒 1，只读）、数据目录 |
| `/settings/extension` | 扩展设置 | 配对令牌（显示已配对状态，不回显 token）、采集扩展/补全桥双在线灯（复用 `BridgePill`）、配对码输入 |
| `/settings/theme` | 主题设置 | 主题切换（复用 `ThemeControl` + `themes`）、跟随系统 |
| `/settings/knowledge` | 个人知识库设置 | 知识库目录、自动抽取开关、数据源管理（占位） |
| `/settings/resume` | 简历设置 | 默认简历版本、投递偏好、招呼语模板占位 |
| `/settings/privacy` | 隐私设置 | 聊天不出本机（恒开、只读）、日志等级、数据导出、清除全部数据 |

---

## 三、Files and Modules

### 修改
- `apps/web/src/routes.ts`：重组路由为 `flowRoutes` / `settingsRoutes`，新增 `/login` 与 8 个设置子路径；`resolveRoute` 支持子路径匹配
- `apps/web/src/App.tsx`：
  - 布局重构为 Sidebar（品牌+新建对话+流程 nav+历史占位+底部设置入口）+ 主内容区
  - 增加登录守卫：未设 PIN 或未解锁时重定向 `/login`
  - 路由分发新增 Agent 中心、各设置页、登录页
- `apps/web/src/styles.css`：新增 Sidebar 样式（参考 `Sidebar.css`）、Agent 欢迎屏、设置页列表、登录页样式；保留并复用现有 token/变量

### 新增
- `apps/web/src/pages_agent.tsx`：`AgentChatPage`（欢迎屏 + 快捷意图 + 输入框 + 占位消息）
- `apps/web/src/pages_settings.tsx`：`SettingsHub` + 8 个设置页（账号/模型/本机/扩展/主题/知识库/简历/隐私）
- `apps/web/src/pages_auth.tsx`：`LoginPage`（本机 PIN 锁屏，含首次设置流程）

### 复用（不修改其业务逻辑）
- `pages_jobs.tsx`（岗位池/采集中心）、`pages_screening.tsx`（筛选池/候选区）
- `theme.ts`（主题）、`lib/capture.ts`（扩展状态）、`BridgePill`

---

## 四、Implementation Steps（依赖顺序）

1. **路由层**：改 `routes.ts`，定义 `flowRoutes`/`settingsRoutes`/`authRoute`，`resolveRoute` 支持子路径回退到父设置页
2. **布局层**：改 `App.tsx` 的 shell 结构——抽 `Sidebar` 组件（品牌+新建对话按钮+流程导航+历史占位+底部设置 popover），主区域渲染路由；保留 `@tanstack/react-query` Provider 与 theme 初始化
3. **登录守卫**：`App.tsx` 顶层读 `localStorage` 的 `jobos.pin`/`jobos.unlocked`；未解锁时渲染 `LoginPage`，不渲染主 shell
4. **登录页**：`pages_auth.tsx` —— PIN 设置/解锁流程，纯前端 localStorage（本机），无网络
5. **Agent 中心**：`pages_agent.tsx` —— 欢迎屏 + 4 快捷卡 + 输入框；提交后 push 占位用户消息 +「Agent 后端待接入」系统消息
6. **设置中心**：`pages_settings.tsx` —— 通用设置页壳（标题 + 描述 + 字段列表），8 个页面按设计字段渲染；主题页复用 `ThemeControl`；扩展页复用 `BridgePill` 与 `fetchExtensionStatus`
7. **样式**：`styles.css` 新增 sidebar/agent/settings/login 区块，复用现有 CSS 变量
8. **校验**：`tsc -b` 类型检查 + `vitest run` 现有测试 + `vite build`

---

## 五、Dependencies and Considerations

- **不新增依赖**：沿用 hash 路由、`@tanstack/react-query`、现有主题系统；不引入 `react-router-dom`、图标库（用 Unicode 符号/文字标签，参考项目的 Icons.tsx 不直接搬，避免额外文件）
- **登录语义**：明确为「本机 PIN 锁屏」，UI 文案避免「账号/注册」等云端暗示；首次设置流程即「注册」
- **数据持久化**：PIN/解锁状态存 `localStorage`（仅本机浏览器），不进后端、不进日志
- **设置页写入**：本期所有设置字段为占位/只读（标注「待后端 API 接入」），不实现前端直接改配置（违反「设置需人审、不可绕过下限」红线）
- **现有流程页不受影响**：采集中心、岗位池、筛选池、候选区等页面组件原样复用，仅换了外层导航壳

---

## 六、Validation

- `npm --prefix apps/web run typecheck` —— 类型全过
- `npm --prefix apps/web test` —— 现有 51 项测试全过
- `npm --prefix apps/web run build` —— 构建成功
- 浏览器手动核对：
  - `/login` 首次设置 PIN → 进入主界面
  - 侧栏「新建对话」按钮、流程导航、底部设置入口可点
  - 8 个设置页均能打开且显示占位字段
  - 现有采集中心/岗位池/筛选池功能正常（回归）
  - 主题切换仍生效

---

## 七、Risks

- **登录守卫破坏现有流程**：若 PIN 状态读取异常可能锁死页面 → 兜底：`localStorage` 解析失败时视为未设置，进入首次设置流程；提供「清除本机数据」重置
- **hash 路由子路径匹配**：`resolveRoute` 当前只精确匹配 → 需改为前缀匹配子路径回退父页，避免设置子路由 404
- **设置页字段误导**：占位 UI 若看起来可编辑会让用户以为能改 → 所有字段加 `disabled` 或明确「待接入」标签，不提供保存按钮
- **AGENTS.md 红线**：本期不触碰后端、不引入云组件、不写聊天原文；Agent 中心只做外壳，不真实调用任何 LLM
