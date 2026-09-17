import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchExtensionStatus,
  importJobs,
  type JobImportResult,
} from './lib/capture'
import { fetchHealth } from './lib/health'
import { CaptureJobsSheet, JobsPage } from './pages_jobs'
import { CandidatesPage, ScreeningPage } from './pages_screening'
import { flowRoutes, resolveRoute, utilityRoutes, type AppRoute } from './routes'
import { applyTheme, resolveTheme, themes, type Theme } from './theme'

function useCurrentRoute(): AppRoute {
  const [route, setRoute] = useState(() => resolveRoute(window.location.hash))

  useEffect(() => {
    const updateRoute = () => setRoute(resolveRoute(window.location.hash))
    window.addEventListener('hashchange', updateRoute)
    return () => window.removeEventListener('hashchange', updateRoute)
  }, [])

  return route
}

function NavigationItem({ route, currentPath }: { route: AppRoute; currentPath: string }) {
  const isCurrent = route.path === currentPath
  return (
    <a className={`nav-item ${isCurrent ? 'active' : ''}`} href={`#${route.path}`} aria-current={isCurrent ? 'page' : undefined}>
      <span className="nav-node" aria-hidden="true" />
      <span className="nav-label">{route.label}</span>
      <span className="nav-short" aria-hidden="true">{route.shortLabel}</span>
    </a>
  )
}

function EmptyState({ route }: { route: AppRoute }) {
  return (
    <div className="empty-state">
      <span className="empty-rule" aria-hidden="true" />
      <h2>{route.emptyTitle}</h2>
      <p>{route.emptyDescription}</p>
      {route.nextPath && route.nextLabel ? <a className="text-action" href={`#${route.nextPath}`}>{route.nextLabel}</a> : null}
    </div>
  )
}

/** 单个扩展角色（列表采集桥 / 岗位池补全桥）的在线状态丸。 */
function BridgePill({
  label,
  online,
  version,
  checking,
}: {
  label: string
  online: boolean
  version?: string
  checking: boolean
}) {
  const text = checking
    ? `${label}检查中`
    : online
      ? `${label} v${version ?? ''}`
      : `${label}未连接`
  return (
    <span
      className={`status-pill ${online ? 'confirmed' : ''}`}
      title={
        online
          ? `${label}已连接（v${version ?? '未知版本'}）`
          : `${label}未连接：MV3 扩展休眠重连时会短暂出现；若持续如此请在 chrome://extensions 检查对应扩展`
      }
    >
      <span aria-hidden="true">{online ? '●' : '○'}</span>
      {text}
    </span>
  )
}

/** 采集中心：扩展配对状态（标题栏右侧）+ 列表 JSON 导入按钮（状态丸左侧）；岗位列表在下一张卡。 */
function CapturePage() {
  const queryClient = useQueryClient()
  const extension = useQuery({
    queryKey: ['extension-status'],
    queryFn: ({ signal }) => fetchExtensionStatus(signal),
    refetchInterval: 4000,
  })
  const inputRef = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)
  const importMutation = useMutation({
    mutationFn: importJobs,
    onSuccess: (result: JobImportResult) => {
      const firstInvalid = result.invalid[0]
      const invalidNote = firstInvalid
        ? `，无效 ${result.invalid.length} 条（如第 ${firstInvalid.index + 1} 项：${firstInvalid.reason}）`
        : ''
      setMessage({
        text: `导入完成：新增 ${result.created} · 合并 ${result.merged}${invalidNote}`,
        error: false,
      })
      void queryClient.invalidateQueries({ queryKey: ['raw-jobs'] })
    },
    onError: (error: Error) => setMessage({ text: error.message, error: true }),
  })

  function submit(file: File | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.json')) {
      setMessage({ text: '请选择扩展导出的 .json 岗位列表文件', error: true })
      return
    }
    importMutation.mutate(file)
  }

  // 两类扩展分开显示：list_bridge 负责翻页直传，pool_bridge 负责入池后的补全。
  const instances = extension.data?.instances ?? []
  const listBridge = [...instances].reverse().find((item) => item.role === 'list_bridge')
  const poolBridge = [...instances].reverse().find((item) => item.role === 'pool_bridge')

  return (
    <div className="sheet-stack">
      <section className="sheet" aria-labelledby="connection-heading">
        <div className="sheet-heading">
          <div><p className="mono-label">LOCAL BRIDGE</p><h2 id="connection-heading">扩展接入与采集</h2></div>
          <div className="heading-actions">
            <input
              ref={inputRef}
              type="file"
              accept=".json,application/json"
              hidden
              onChange={(event) => submit(event.target.files?.[0])}
            />
            <button
              type="button"
              className="primary-action"
              onClick={() => inputRef.current?.click()}
              disabled={importMutation.isPending}
              title="导入扩展导出的岗位列表 JSON（≤5MB，≤500 条）；重复导入按 (source, ext_id) 幂等合并"
            >
              {importMutation.isPending ? '导入中…' : '选择文件导入'}
            </button>
            <BridgePill
              label="采集扩展"
              online={Boolean(listBridge)}
              version={listBridge?.extension_version}
              checking={extension.isPending}
            />
            <BridgePill
              label="补全桥"
              online={Boolean(poolBridge)}
              version={poolBridge?.extension_version}
              checking={extension.isPending}
            />
          </div>
        </div>
        {message ? (
          <div className="sheet-body">
            <p className={`form-message ${message.error ? 'error' : ''}`}>{message.text}</p>
          </div>
        ) : null}
      </section>

      <CaptureJobsSheet />
    </div>
  )
}

function ThemeControl({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  return (
    <label className="theme-control">
      <span>主题</span>
      <select value={theme} onChange={(event) => onChange(resolveTheme(event.target.value))}>
        {themes.map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
    </label>
  )
}

function SettingsPage({ theme, onThemeChange }: { theme: Theme; onThemeChange: (theme: Theme) => void }) {
  return (
    <section className="sheet" aria-labelledby="settings-heading">
      <div className="sheet-heading">
        <div><p className="mono-label">READ-ONLY BASELINE</p><h2 id="settings-heading">当前安全基线</h2></div>
        <span className="status-pill neutral"><span aria-hidden="true">○</span>只读</span>
      </div>
      <dl className="status-table settings-table">
        <div><dt>界面主题</dt><dd><ThemeControl theme={theme} onChange={onThemeChange} /></dd></div>
        <div><dt>采集间隔下限</dt><dd><code>1800 ms</code></dd></div>
        <div><dt>采集并发</dt><dd><code>1</code></dd></div>
        <div><dt>模型密钥</dt><dd>不进入前端，状态接口尚未接入</dd></div>
        <div><dt>备份</dt><dd>尚无可用状态源</dd></div>
      </dl>
      <div className="notice"><strong>设置暂不可编辑。</strong><span>后续必须通过受校验的本机 API 保存，不能在浏览器中绕过下限。</span></div>
    </section>
  )
}

function HomePage({ isOnline }: { isOnline: boolean }) {
  return (
    <section className="desk-list" aria-labelledby="desk-heading">
      <div className="desk-header"><p className="mono-label">NEXT SAFE STEP</p><h2 id="desk-heading">建立本机连接</h2></div>
      <div className="desk-row">
        <span className={`evidence-symbol ${isOnline ? 'confirmed' : ''}`} aria-hidden="true">{isOnline ? '●' : '○'}</span>
        <div><strong>{isOnline ? '本机 API 已就绪' : '本机 API 尚未连接'}</strong><p>检查扩展配对状态后，再进入任何采集工作。</p></div>
        <a className="primary-action" href="#/capture">查看扩展接入</a>
      </div>
    </section>
  )
}

/** 卡片即页面主体的路由：不渲染全局页头。 */
const PLAIN_PAGES = new Set(['/screening', '/capture', '/jobs'])

export function App() {
  const route = useCurrentRoute()
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(window.localStorage.getItem('jobos.theme')))
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => fetchHealth(signal) })
  const isOnline = health.data?.status === 'ok'

  useEffect(() => applyTheme(theme), [theme])

  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand" href="#/" aria-label="JobOS 今日案头">
          <span className="brand-mark" aria-hidden="true">JO</span><span className="brand-name">JobOS</span>
        </a>
        <nav className="funnel-nav" aria-label="求职流程">
          {flowRoutes.map((item) => <NavigationItem key={item.path} route={item} currentPath={route.path} />)}
        </nav>
        <nav className="utility-nav" aria-label="工具与设置">
          {utilityRoutes.map((item) => <NavigationItem key={item.path} route={item} currentPath={route.path} />)}
        </nav>
        <p className="privacy-note"><span aria-hidden="true">●</span>数据留在本机</p>
      </aside>

      <div className="work-area">
        <header className="topbar" aria-label="系统状态">
          <a href="#/capture" className="top-status"><span className={`status-dot ${isOnline ? 'online' : ''}`} aria-hidden="true" /><span>扩展</span><strong>等待状态源</strong></a>
          <span className="top-status"><span className="mono-label">安全基线</span><strong>≥1800ms · 并发1</strong></span>
          <span className="top-status optional"><span>AI</span><strong>未配置</strong></span>
          <span className="top-status optional"><span>备份</span><strong>无记录</strong></span>
          <ThemeControl theme={theme} onChange={setTheme} />
          <span className={`api-state ${isOnline ? 'online' : ''}`} role="status">{health.isPending ? 'API 检查中' : isOnline ? 'API 正常' : 'API 未连接'}</span>
        </header>

        <div className="mobile-readonly" role="note">窄屏为只读模式，请在桌面端完成编辑或确认。</div>

        <div className={`page-grid${PLAIN_PAGES.has(route.path) ? ' no-context-rail' : ''}`}>
          <main id="workspace" className="page-content">
            {PLAIN_PAGES.has(route.path) ? null : (
              <header className="page-heading">
                <p className="mono-label">{route.eyebrow}</p><h1>{route.title}</h1><p>{route.description}</p>
              </header>
            )}
            {route.path === '/' ? <HomePage isOnline={isOnline} /> : null}
            {route.path === '/capture' ? <CapturePage /> : null}
            {route.path === '/jobs' ? <JobsPage /> : null}
            {route.path === '/screening' ? <ScreeningPage /> : null}
            {route.path === '/shortlist' ? <CandidatesPage /> : null}
            {route.path === '/settings' ? <SettingsPage theme={theme} onThemeChange={setTheme} /> : null}
            {route.emptyTitle ? <EmptyState route={route} /> : null}
          </main>

          <aside className="context-rail" aria-label="当前页面边界">
            <p className="mono-label">BOUNDARY</p><h2>当前实现边界</h2>
            <ul className="boundary-list">
              <li><span>●</span><div><strong>本机运行</strong><p>只读取 loopback 健康状态。</p></div></li>
              <li><span>◐</span><div><strong>状态待接入</strong><p>无来源的数据不展示数字。</p></div></li>
              <li><span>○</span><div><strong>无外部动作</strong><p>当前外壳不会访问招聘站点。</p></div></li>
            </ul>
            <div className="context-code"><span>route</span><code>{route.path}</code></div>
          </aside>
        </div>
      </div>
    </div>
  )
}
