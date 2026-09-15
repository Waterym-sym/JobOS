import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  abortCapture,
  createCapture,
  fetchExtensionStatus,
  fetchRawJobs,
  type BatchInfo,
  type RawJobItem,
} from './lib/capture'
import { fetchHealth } from './lib/health'
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

function RawJobsCard({ items, isPending }: { items: RawJobItem[]; isPending: boolean }) {
  return (
    <div className="field full">
      <label>最近入池岗位（raw_job）</label>
      {isPending ? (
        <p className="form-message">读取中…</p>
      ) : items.length === 0 ? (
        <p className="form-message">尚无岗位落库。触发采集或在扩展侧一键抓取后，数据会出现在这里。</p>
      ) : (
        <table className="raw-table">
          <thead>
            <tr><th>标题</th><th>公司</th><th>城市</th><th>薪资</th><th className="mono">ext_id</th></tr>
          </thead>
          <tbody>
            {items.map((job) => (
              <tr key={job.id}>
                <td>{job.title ?? '—'}</td>
                <td>{job.company ?? '—'}</td>
                <td>{job.city ?? '—'}</td>
                <td>{job.salary_text ?? '—'}</td>
                <td className="mono">{job.ext_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function CapturePage() {
  const extension = useQuery({
    queryKey: ['extension-status'],
    queryFn: ({ signal }) => fetchExtensionStatus(signal),
    refetchInterval: 4000,
  })
  const rawJobs = useQuery({
    queryKey: ['raw-jobs'],
    queryFn: ({ signal }) => fetchRawJobs(signal),
    refetchInterval: 6000,
  })
  const [kind, setKind] = useState<'list' | 'detail'>('list')
  const [maxItems, setMaxItems] = useState('30')
  const [delayMs, setDelayMs] = useState('1800')
  const [extIdsText, setExtIdsText] = useState('')
  const [detailLimit, setDetailLimit] = useState('15')
  const [activeBatch, setActiveBatch] = useState<BatchInfo | null>(null)
  const [formMessage, setFormMessage] = useState<{ text: string; error: boolean } | null>(null)

  const captureMutation = useMutation({
    mutationFn: createCapture,
    onSuccess: (batch) => {
      setActiveBatch(batch)
      setFormMessage({ text: `批次已建立：${batch.id.slice(0, 8)} · ${batch.status}`, error: false })
      void extension.refetch()
      void rawJobs.refetch()
    },
    onError: (err: Error) => setFormMessage({ text: err.message, error: true }),
  })
  const abortMutation = useMutation({
    mutationFn: abortCapture,
    onSuccess: (batch) => {
      setActiveBatch(batch)
      setFormMessage({ text: `批次已中止：${batch.id.slice(0, 8)}`, error: false })
    },
    onError: (err: Error) => setFormMessage({ text: err.message, error: true }),
  })

  const paired = extension.data?.paired === true
  const instance = extension.data?.paired ? extension.data : null
  const batchRunning = activeBatch ? ['queued', 'running'].includes(activeBatch.status) : false

  async function submitCapture() {
    const delay = Number(delayMs)
    if (Number.isNaN(delay) || delay < 1800) {
      setFormMessage({ text: '节流间隔不得低于 1800ms', error: true })
      return
    }
    if (kind === 'list') {
      const items = Number(maxItems)
      if (Number.isNaN(items) || items < 1) {
        setFormMessage({ text: 'max_items 需为正整数（1-500）', error: true })
        return
      }
      captureMutation.mutate({
        kind: 'list',
        max_items: Math.min(Math.max(items, 1), 500),
        detail_limit: 15,
        delay_ms: delay,
      })
    } else {
      const ids = extIdsText.split(/[\s,，]+/).filter(Boolean)
      if (ids.length === 0) {
        setFormMessage({ text: '详情采集必须提供 ext_ids', error: true })
        return
      }
      const limit = Number(detailLimit) || ids.length
      captureMutation.mutate({
        kind: 'detail',
        ext_ids: ids,
        max_items: Math.min(ids.length, 500),
        detail_limit: Math.min(Math.max(limit, 1), 100),
        delay_ms: delay,
      })
    }
  }

  return (
    <section className="sheet" aria-labelledby="connection-heading">
      <div className="sheet-heading">
        <div><p className="mono-label">LOCAL BRIDGE</p><h2 id="connection-heading">扩展接入与采集</h2></div>
        <span className={`status-pill ${paired ? 'confirmed' : ''}`}>
          <span aria-hidden="true">{paired ? '●' : '○'}</span>
          {extension.isPending ? '检查中' : paired ? '扩展已配对' : '扩展未接入'}
        </span>
      </div>

      <div className="capture-body">
        <dl className="status-table" style={{ borderBottom: '1px solid var(--hairline)' }}>
          <div>
            <dt>扩展实例</dt>
            <dd>
              {instance ? (
                <>v{instance.extension_version} · {instance.instance_id.slice(0, 8)}<br />
                  <span className="tag-micro">connected {instance.connected_at.slice(11, 19)}</span>
                </>
              ) : (
                '未配对：在扩展「选项」页填入网关地址与配对码'
              )}
            </dd>
          </div>
          <div>
            <dt>Gateway</dt>
            <dd><code>ws://127.0.0.1:8788/ws</code></dd>
          </div>
          <div>
            <dt>安全基线</dt>
            <dd>间隔 ≥1800ms + 抖动 · 并发恒 1 · 不自动翻页/发送</dd>
          </div>
        </dl>

        <div className="notice">
          <strong>配对码不会发送到浏览器。</strong>
          <span>请从本机 <code>data/config/pairing.token</code> 复制到扩展选项页；完成配对后即可在这里查看连接状态。</span>
        </div>

        <div className="capture-grid">
          <div className="field">
            <label>采集类型</label>
            <div className="kind-toggle">
              <button type="button" className={kind === 'list' ? 'active' : ''} onClick={() => setKind('list')}>列表</button>
              <button type="button" className={kind === 'detail' ? 'active' : ''} onClick={() => setKind('detail')}>详情</button>
            </div>
          </div>
          <div className="field">
            <label>节流间隔 delay_ms（≥1800）</label>
            <input value={delayMs} onChange={(e) => setDelayMs(e.target.value)} inputMode="numeric" />
          </div>
          {kind === 'list' ? (
            <div className="field">
              <label>max_items（1-500）</label>
              <input value={maxItems} onChange={(e) => setMaxItems(e.target.value)} inputMode="numeric" />
            </div>
          ) : (
            <>
              <div className="field full">
                <label>ext_ids（逗号/换行/空格分隔）</label>
                <input value={extIdsText} onChange={(e) => setExtIdsText(e.target.value)} placeholder="ext_id_1, ext_id_2 …" />
              </div>
              <div className="field">
                <label>detail_limit（1-100）</label>
                <input value={detailLimit} onChange={(e) => setDetailLimit(e.target.value)} inputMode="numeric" />
              </div>
            </>
          )}
          <RawJobsCard items={rawJobs.data ?? []} isPending={rawJobs.isPending} />
        </div>

        <div className="capture-actions">
          <button
            type="button"
            className="primary-action"
            onClick={submitCapture}
            disabled={captureMutation.isPending || !paired}
          >
            {captureMutation.isPending ? '下发中…' : '下发采集命令'}
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={() => activeBatch && abortMutation.mutate(activeBatch.id)}
            disabled={!batchRunning || abortMutation.isPending}
          >
            中止当前批次
          </button>
          {formMessage ? <p className={`form-message ${formMessage.error ? 'error' : ''}`}>{formMessage.text}</p> : null}
          {!paired && !extension.isPending ? <p className="form-message error">扩展未配对，命令无法下发。</p> : null}
        </div>
      </div>
    </section>
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

        <div className="page-grid">
          <main id="workspace" className="page-content">
            <header className="page-heading">
              <p className="mono-label">{route.eyebrow}</p><h1>{route.title}</h1><p>{route.description}</p>
            </header>
            {route.path === '/' ? <HomePage isOnline={isOnline} /> : null}
            {route.path === '/capture' ? <CapturePage /> : null}
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
