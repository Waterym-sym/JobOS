export type RouteGroup = 'flow' | 'settings' | 'auth'

export type AppRoute = {
  path: string
  label: string
  shortLabel: string
  eyebrow: string
  title: string
  description: string
  group: RouteGroup
  emptyTitle?: string
  emptyDescription?: string
  nextPath?: string
  nextLabel?: string
}

// 流程导航：从上到下显示在侧栏中部
export const flowRoutes: readonly AppRoute[] = [
  { path: '/', label: '新建对话', shortLabel: '对话', eyebrow: 'Agent', title: '新建对话', description: '与本机 Agent 协作：筛选岗位、诊断简历、生成投递包、复盘分析。', group: 'flow' },
  { path: '/capture', label: '采集中心', shortLabel: '采集', eyebrow: 'Capture', title: '扩展接入与采集状态', description: '先确认本机链路，再由你在浏览器中人工启动采集。', group: 'flow' },
  { path: '/jobs', label: '岗位池', shortLabel: '岗位', eyebrow: 'Job pool', title: '岗位池', description: '浏览已导入的岗位并人工入池；补全完成的岗位自动流向筛选池。', group: 'flow' },
  { path: '/screening', label: '筛选池', shortLabel: '筛选', eyebrow: 'Screening pool', title: '筛选池', description: '补全完成的岗位自动流入；逐条对照 JD 与公司画像，人工决定是否进入候选区。', group: 'flow' },
  { path: '/shortlist', label: '候选区', shortLabel: '候选', eyebrow: 'Shortlist', title: '候选决策', description: '候选区是进入投递准备的唯一入口，决定始终由你确认。', group: 'flow' },
  { path: '/packages', label: '投递包', shortLabel: '投包', eyebrow: 'Application package', title: '投递材料准备', description: '经确认的候选岗位生成投递包；系统不会替你发送。', group: 'flow', emptyTitle: '尚未创建投递包', emptyDescription: '投递包只能从已确认的候选岗位创建。' },
  { path: '/events', label: '事件确认台', shortLabel: '确认', eyebrow: 'Review queue', title: '事件草稿确认', description: '草稿只有经你确认后，才会投影到求职状态。', group: 'flow', emptyTitle: '没有待确认事件', emptyDescription: '聊天回采能力尚未进入实现阶段；当前不会生成或投影任何事件。' },
  { path: '/retrospective', label: '复盘与漏斗', shortLabel: '复盘', eyebrow: 'Retrospective', title: '复盘与漏斗', description: '所有数字都需要能下钻到本机明细并完成对账。', group: 'flow', emptyTitle: '还没有可复盘的终态记录', emptyDescription: '形成经确认的状态记录后，这里才会展示漏斗与复盘。' },
] as const

// 设置导航：显示在侧栏底部设置组
export const settingsRoutes: readonly AppRoute[] = [
  { path: '/settings', label: '账号设置', shortLabel: '账号', eyebrow: 'Account', title: '账号设置', description: '本机身份与解锁方式；数据只留在本机。', group: 'settings' },
  { path: '/settings/model', label: '模型设置', shortLabel: '模型', eyebrow: 'Model', title: '模型设置', description: 'LLM 提供商与密钥；密钥不回显、不离开本机。', group: 'settings' },
  { path: '/settings/local', label: '本机设置', shortLabel: '本机', eyebrow: 'Local', title: '本机设置', description: 'API 端口、采集下限等安全基线；下限不可在前端放宽。', group: 'settings' },
  { path: '/settings/extension', label: '扩展设置', shortLabel: '扩展', eyebrow: 'Extension', title: '扩展设置', description: '浏览器扩展配对状态与配对令牌；令牌不回显。', group: 'settings' },
  { path: '/settings/theme', label: '主题设置', shortLabel: '主题', eyebrow: 'Theme', title: '主题设置', description: '界面主题与外观偏好。', group: 'settings' },
  { path: '/settings/knowledge', label: '知识库设置', shortLabel: '知识', eyebrow: 'Knowledge', title: '个人知识库设置', description: '职业资产目录与抽取规则。', group: 'settings' },
  { path: '/settings/resume', label: '简历设置', shortLabel: '简历', eyebrow: 'Resume', title: '简历设置', description: '默认简历版本与投递偏好。', group: 'settings' },
  { path: '/settings/privacy', label: '隐私设置', shortLabel: '隐私', eyebrow: 'Privacy', title: '隐私设置', description: '数据出境控制、日志等级与本机数据管理。', group: 'settings' },
] as const

export const authRoute: AppRoute = {
  path: '/login',
  label: '解锁',
  shortLabel: '解锁',
  eyebrow: 'Unlock',
  title: '本机解锁',
  description: '输入本机 PIN 解锁 JobOS。',
  group: 'auth',
}

export const routes: readonly AppRoute[] = [
  authRoute,
  ...flowRoutes,
  ...settingsRoutes,
  // 保留旧 utility 路由（模板/知识库）以便入口仍可达
  { path: '/templates', label: '模板中心', shortLabel: '模板', eyebrow: 'Templates', title: '模板中心', description: '模板只定义版式，不在模板内写入事实文本。', group: 'settings', emptyTitle: '模板库尚未接入', emptyDescription: '许可证检查通过后，这里会显示分级模板。' },
]

export function resolveRoute(hash: string): AppRoute {
  const rawPath = hash.startsWith('#') ? hash.slice(1) : hash
  const path = rawPath.split('?')[0] || '/'
  // 精确匹配
  const exact = routes.find((route) => route.path === path)
  if (exact) return exact
  // 设置子路径前缀匹配：未定义的子路径回退到 /settings
  if (path.startsWith('/settings')) {
    return settingsRoutes[0]!
  }
  // 未知路径回退到首页
  return flowRoutes[0]!
}

export function isSettingsPath(path: string): boolean {
  return path.startsWith('/settings')
}
