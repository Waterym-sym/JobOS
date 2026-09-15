import { useQuery } from '@tanstack/react-query'

import { fetchHealth } from './lib/health'

const stages = [
  ['采集', '等待扩展接入'],
  ['筛选', '规则集尚未运行'],
  ['候选', '0 个岗位'],
  ['投递准备', '由你确认后生成'],
] as const

export function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => fetchHealth(signal) })
  const isOnline = health.data?.status === 'ok'

  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand" href="#workspace" aria-label="JobOS 工作台首页">
          <span className="brand-mark" aria-hidden="true">J</span>
          <span>JobOS</span>
        </a>
        <nav aria-label="主要导航">
          <a className="nav-item active" href="#workspace">工作台</a>
          <span className="nav-item disabled">岗位池</span>
          <span className="nav-item disabled">候选区</span>
          <span className="nav-item disabled">职业资产</span>
        </nav>
        <div className="privacy-note">
          <span className="privacy-dot" aria-hidden="true" />
          数据留在本机
        </div>
      </aside>

      <main id="workspace">
        <header className="topline">
          <div>
            <p className="eyebrow">本地求职闭环 / P1 框架</p>
            <h1>先把每一步<br />变得可信。</h1>
          </div>
          <div className={`system-state ${isOnline ? 'online' : ''}`} role="status">
            <span className="state-lamp" aria-hidden="true" />
            <div>
              <small>本地服务</small>
              <strong>{health.isPending ? '正在检查' : isOnline ? '运行正常' : '尚未连接'}</strong>
            </div>
          </div>
        </header>

        <section className="workspace-grid" aria-label="工作区概况">
          <article className="flow-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">今日路径</p>
                <h2>从采集到人工确认</h2>
              </div>
              <span className="local-chip">LOCAL ONLY</span>
            </div>
            <ol className="evidence-flow">
              {stages.map(([name, detail], index) => (
                <li key={name}>
                  <span className="flow-index">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{name}</strong>
                    <p>{detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </article>

          <aside className="guard-panel">
            <p className="eyebrow">系统边界</p>
            <h2>决定权始终在你手里</h2>
            <p>系统负责整理证据、解释差距并准备材料。所有对外操作均保留为人工步骤。</p>
            <dl>
              <div><dt>网络</dt><dd>Loopback</dd></div>
              <div><dt>证据链</dt><dd>强制追溯</dd></div>
              <div><dt>外部动作</dt><dd>人工确认</dd></div>
            </dl>
          </aside>
        </section>
      </main>
    </div>
  )
}
