export type RouteGroup = 'flow' | 'utility'

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

export const routes: readonly AppRoute[] = [
  { path: '/', label: '今日案头', shortLabel: '案头', eyebrow: 'Today desk', title: '今天要处理什么', description: '只显示有来源、能对账的本机待办。', group: 'flow' },
  { path: '/capture', label: '采集中心', shortLabel: '采集', eyebrow: 'Capture', title: '扩展接入与采集状态', description: '先确认本机链路，再由你在浏览器中人工启动采集。', group: 'flow' },
  { path: '/jobs', label: '岗位池', shortLabel: '岗位', eyebrow: 'Job pool', title: '岗位池', description: '浏览已导入的岗位并人工入池；补全完成的岗位自动流向筛选池。', group: 'flow' },
  { path: '/screening', label: '筛选池', shortLabel: '筛选', eyebrow: 'Screening pool', title: '筛选池', description: '补全完成的岗位自动流入；逐条对照 JD 与公司画像，人工决定是否进入候选区。', group: 'flow' },
  { path: '/shortlist', label: '候选区', shortLabel: '候选', eyebrow: 'Shortlist', title: '候选决策', description: '候选区是进入投递准备的唯一入口，决定始终由你确认。', group: 'flow' },
  { path: '/packages', label: '投递包', shortLabel: '投包', eyebrow: 'Application package', title: '投递材料准备', description: '这里将呈现经确认的简历版本、招呼语草稿与 Guard 结果。', group: 'flow', emptyTitle: '尚未创建投递包', emptyDescription: '投递包只能从已确认的候选岗位创建；系统不会替你发送。' },
  { path: '/events', label: '事件确认台', shortLabel: '确认', eyebrow: 'Review queue', title: '事件草稿确认', description: '草稿只有经你确认后，才会投影到求职状态。', group: 'flow', emptyTitle: '没有待确认事件', emptyDescription: '聊天回采能力尚未进入实现阶段；当前不会生成或投影任何事件。' },
  { path: '/retrospective', label: '复盘与漏斗', shortLabel: '复盘', eyebrow: 'Retrospective', title: '复盘与漏斗', description: '所有数字都需要能下钻到本机明细并完成对账。', group: 'flow', emptyTitle: '还没有可复盘的终态记录', emptyDescription: '形成经确认的状态记录后，这里才会展示漏斗与复盘。' },
  { path: '/templates', label: '模板中心', shortLabel: '模板', eyebrow: 'Templates', title: '模板中心', description: '模板只定义版式，不在模板内写入事实文本。', group: 'utility', emptyTitle: '模板库尚未接入', emptyDescription: '导入与许可证检查通过后，这里会显示分级模板；3D 画廊默认关闭。' },
  { path: '/knowledge', label: '知识库', shortLabel: '知识', eyebrow: 'Knowledge base', title: '职业资产与证据', description: '事实、证据和 AI 草稿保持清晰分层。', group: 'utility', emptyTitle: '还没有职业资产', emptyDescription: '知识库导入尚未开始；未经确认的抽取内容不会成为事实。' },
  { path: '/settings', label: '设置', shortLabel: '设置', eyebrow: 'Local settings', title: '本机设置', description: '敏感值不回显，安全下限不可放宽。', group: 'utility' },
] as const

export const flowRoutes = routes.filter((route) => route.group === 'flow')
export const utilityRoutes = routes.filter((route) => route.group === 'utility')

export function resolveRoute(hash: string): AppRoute {
  const rawPath = hash.startsWith('#') ? hash.slice(1) : hash
  const path = rawPath.split('?')[0] || '/'
  return routes.find((route) => route.path === path) ?? routes[0]!
}
