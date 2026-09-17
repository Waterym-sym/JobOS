import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchExtensionStatus,
  importJobs,
  type JobImportResult,
} from './lib/capture'
import { fetchHealth } from './lib/health'
import { CaptureJobsSheet, JobsPage } from './pages_jobs'
import { CandidatesPage, ScreeningPage } from './pages_screening'
import { flowRoutes, resolveRoute, settingsRoutes, type AppRoute } from './routes'
import { resolveTheme, themes, type Theme } from './theme'
import { AgentChatPage } from './pages_agent'
import { getMe, getProfile, logout, type Account } from './lib/account'
import { AccountLoginPage, AccountSettings } from './pages_account'
import {
  applyTheme,
  renderSettingsPage,
  ThemeControl,
} from './pages_settings'

const OnboardingFlow = lazy(() => import('./pages_onboarding'))

/* ----------------------------------------------------------- helpers */

function useCurrentRoute(): AppRoute {
  const [route, setRoute] = useState(() => resolveRoute(window.location.hash))
  useEffect(() => {
    const updateRoute = () => setRoute(resolveRoute(window.location.hash))
    window.addEventListener('hashchange', updateRoute)
    return () => window.removeEventListener('hashchange', updateRoute)
  }, [])
  return route
}

function go(path: string) {
  window.location.hash = path
}

/* ----------------------------------------------------------- Sidebar */

function Sidebar({
  currentPath,
  nickname,
  onLogout,
}: {
  currentPath: string
  nickname: string
  onLogout: () => void
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <div className="sidebar__brand">
          <span className="sidebar__brand-mark" aria-hidden="true">JO</span>
          <span className="sidebar__brand-text">JobOS</span>
        </div>
      </div>

      <button
        type="button"
        className="sidebar__new-chat"
        onClick={() => go('/')}
      >
        <span aria-hidden="true">＋</span>
        <span>新建对话</span>
      </button>

      <nav className="sidebar__nav" aria-label="求职流程">
        {flowRoutes.map((item) => {
          const isActive =
            item.path === '/'
              ? currentPath === '/'
              : currentPath === item.path
          return (
            <button
              key={item.path}
              type="button"
              className={`sidebar__nav-item ${isActive ? 'sidebar__nav-item--active' : ''}`}
              onClick={() => go(item.path)}
            >
              <span className="sidebar__nav-label">{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div className="sidebar__history">
        <span className="sidebar__history-label">历史对话</span>
        <ul className="sidebar__history-list">
          <li>
            <span className="sidebar__history-empty">暂无会话</span>
          </li>
        </ul>
      </div>

      <div className="sidebar__footer" ref={settingsRef}>
        <button
          type="button"
          className={`sidebar__settings-btn ${settingsOpen ? 'sidebar__settings-btn--open' : ''}`}
          onClick={() => setSettingsOpen((v) => !v)}
          aria-expanded={settingsOpen}
          aria-haspopup="true"
        >
          <span className="sidebar__avatar" aria-hidden="true">
            {nickname.slice(0, 1)}
          </span>
          <span className="sidebar__username">{nickname}</span>
          <span className="sidebar__chev" aria-hidden="true">▾</span>
        </button>

        {settingsOpen ? (
          <div className="sidebar__settings-menu" role="menu">
            <div className="sidebar__settings-group-label">设置</div>
            {settingsRoutes.map((item) => (
              <button
                key={item.path}
                type="button"
                role="menuitem"
                className="sidebar__settings-item"
                onClick={() => {
                  go(item.path)
                  setSettingsOpen(false)
                }}
              >
                {item.label}
              </button>
            ))}
            <div className="sidebar__settings-divider" />
            <button
              type="button"
              role="menuitem"
              className="sidebar__settings-item sidebar__settings-item--danger"
              onClick={() => {
                setSettingsOpen(false)
                onLogout()
              }}
            >
              退出登录
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  )
}

/* ----------------------------------------------------------- Capture */

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

  const instances = extension.data?.instances ?? []
  const listBridge = [...instances].reverse().find((item) => item.role === 'list_bridge')
  const poolBridge = [...instances].reverse().find((item) => item.role === 'pool_bridge')

  const pill = (label: string, online: boolean, version?: string) => (
    <span
      className={`status-pill ${online ? 'confirmed' : ''}`}
      title={online ? `${label}已连接（v${version ?? '未知版本'}）` : `${label}未连接`}
    >
      <span aria-hidden="true">{online ? '●' : '○'}</span>
      {extension.isPending ? `${label}检查中` : online ? `${label} v${version ?? ''}` : `${label}未连接`}
    </span>
  )

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
              title="导入扩展导出的岗位列表 JSON"
            >
              {importMutation.isPending ? '导入中…' : '选择文件导入'}
            </button>
            {pill('采集扩展', Boolean(listBridge), listBridge?.extension_version)}
            {pill('补全桥', Boolean(poolBridge), poolBridge?.extension_version)}
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

function EmptyState({ route }: { route: AppRoute }) {
  return (
    <div className="empty-state">
      <span className="empty-rule" aria-hidden="true" />
      <h2>{route.emptyTitle}</h2>
      <p>{route.emptyDescription}</p>
    </div>
  )
}

/* ----------------------------------------------------------- App shell */

export function App() {
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(window.localStorage.getItem('jobos.theme')))
  const queryClient = useQueryClient()
  const [accountError, setAccountError] = useState('')
  const route = useCurrentRoute()
  const accountQuery = useQuery({ queryKey: ['me'], queryFn: getMe, retry: false })
  const account = accountQuery.data
  const profileQuery = useQuery({ queryKey: ['profile', account?.id], queryFn: getProfile,
    enabled: account?.role === 'seeker', retry: false })
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => fetchHealth(signal) })
  const isOnline = health.data?.status === 'ok'

  useEffect(() => applyTheme(theme), [theme])

  if (accountQuery.isPending) return <div className="account-loading">正在验证账号…</div>
  if (!account) return <AccountLoginPage onLogin={(signedIn) => {
    queryClient.setQueryData(['me'], signedIn)
    window.location.hash = '/'
  }} />

  const handleLogout = async () => {
    try {
      await logout()
      queryClient.clear()
      queryClient.setQueryData(['me'], null)
      window.location.hash = '/login'
    } catch {
      setAccountError('退出失败，请检查连接后重试。')
    }
  }

  if (account.role === 'recruiter') return <div className="recruiter-workbench">
    <div className="recruiter-workbench__header"><strong>JobOS · 招聘者工作台</strong>
      <button type="button" onClick={() => void handleLogout()}>退出登录</button></div>
    <div className="recruiter-workbench__body">{accountError ? <p role="alert">{accountError}</p> : null}<h1>欢迎，{account.display_name}</h1>
      <p>招聘业务流程尚未开放。此工作台与求职者数据和流程隔离。</p>
      <AccountSettings account={account} onAccountChange={(next: Account) => { queryClient.setQueryData<Account>(['me'], next) }}
        onLogout={() => { queryClient.clear(); queryClient.setQueryData(['me'], null) }} />
    </div></div>

  if (profileQuery.isPending) return <div className="account-loading">正在加载个人资料…</div>
  if (profileQuery.isError) return <div className="account-loading" role="alert">无法加载个人资料，请稍后刷新。</div>
  if (profileQuery.data?.onboarding_step !== 'complete') return <Suspense fallback={<div className="account-loading">正在载入入门流程…</div>}>
    <OnboardingFlow onComplete={() => { void queryClient.invalidateQueries({ queryKey: ['profile', account.id] }) }}
      onBackToLogin={() => { void handleLogout() }} />
  </Suspense>

  const nickname = account.display_name || account.email
  const legacyAllowed = account.is_admin

  const isSettings = route.path.startsWith('/settings')

  return (
    <div className="app-shell">
      <Sidebar
        currentPath={route.path}
        nickname={nickname}
        onLogout={() => void handleLogout()}
      />

      <div className="work-area">
        <header className="topbar" aria-label="系统状态">
          <span className="top-status"><span className={`status-dot ${isOnline ? 'online' : ''}`} aria-hidden="true" /><span>API</span><strong>{isOnline ? '正常' : '未连接'}</strong></span>
          <span className="top-status"><span className="mono-label">安全基线</span><strong>≥1800ms · 并发1</strong></span>
          <span className="top-status optional"><span>AI</span><strong>未配置</strong></span>
          {isSettings ? <ThemeControl theme={theme} onChange={setTheme} /> : null}
        </header>

        <main className="page-content">
          {accountError ? <p role="alert" className="form-message error">{accountError}</p> : null}
          {route.path === '/settings' ? <AccountSettings account={account}
            onAccountChange={(next: Account) => { queryClient.setQueryData<Account>(['me'], next) }}
            onLogout={() => { queryClient.clear(); queryClient.setQueryData(['me'], null) }} /> : null}
          {!legacyAllowed && route.path !== '/settings' ? <div className="empty-state"><span className="empty-rule" aria-hidden="true" />
            <h2>此流程暂未开放</h2><p>多用户隔离仍在验收中。你的资料不会进入旧版本机流程。</p></div> : null}
          {legacyAllowed && route.path === '/' ? <AgentChatPage /> : null}
          {legacyAllowed && route.path === '/capture' ? <CapturePage /> : null}
          {legacyAllowed && route.path === '/jobs' ? <JobsPage /> : null}
          {legacyAllowed && route.path === '/screening' ? <ScreeningPage /> : null}
          {legacyAllowed && route.path === '/shortlist' ? <CandidatesPage /> : null}
          {legacyAllowed && route.path === '/packages' && route.emptyTitle ? <EmptyState route={route} /> : null}
          {legacyAllowed && route.path === '/events' && route.emptyTitle ? <EmptyState route={route} /> : null}
          {legacyAllowed && route.path === '/retrospective' && route.emptyTitle ? <EmptyState route={route} /> : null}
          {legacyAllowed && route.path === '/templates' && route.emptyTitle ? <EmptyState route={route} /> : null}
          {legacyAllowed && isSettings && route.path !== '/settings' ? renderSettingsPage(route.path, theme, setTheme) : null}
        </main>
      </div>
    </div>
  )
}
