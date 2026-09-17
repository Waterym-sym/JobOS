import { useQuery } from '@tanstack/react-query'

import { fetchExtensionStatus } from './lib/capture'
import { applyTheme, resolveTheme, themes, type Theme } from './theme'

/**
 * 设置中心：8 个设置页。
 * 本期全部为占位 UI（标注「待后端 API 接入」），不实现前端写入——
 * 遵守 AGENTS.md：模型密钥、采集下限、配对令牌等不可在前端绕过。
 */

/* ------------------------------------------------------------------ shared */

export function ThemeControl({
  theme,
  onChange,
}: {
  theme: Theme
  onChange: (theme: Theme) => void
}) {
  return (
    <label className="settings-field">
      <span>界面主题</span>
      <select
        value={theme}
        onChange={(event) => onChange(resolveTheme(event.target.value))}
      >
        {themes.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  )
}

/** 单个扩展角色在线状态丸。 */
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
          : `${label}未连接：MV3 扩展休眠重连时会短暂出现`
      }
    >
      <span aria-hidden="true">{online ? '●' : '○'}</span>
      {text}
    </span>
  )
}

function SettingsShell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <section className="sheet" aria-labelledby="settings-heading">
      <div className="sheet-heading">
        <div>
          <p className="mono-label">{eyebrow}</p>
          <h2 id="settings-heading">{title}</h2>
        </div>
      </div>
      <div className="sheet-body">
        <p className="settings-description">{description}</p>
        {children}
        <p className="settings-notice">
          以上为占位 UI，真实保存需后端受校验 API 接入；安全下限不可在前端绕过。
        </p>
      </div>
    </section>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      {children}
      {hint ? <em className="settings-hint">{hint}</em> : null}
    </label>
  )
}

/* ---------------------------------------------------------------- pages */

export function AccountSettingsPage() {
  return (
    <SettingsShell
      eyebrow="ACCOUNT"
      title="账号设置"
      description="本机身份与解锁方式。数据只留在本机浏览器，无云端账号。"
    >
      <div className="settings-profile">
        <span className="settings-avatar" aria-hidden="true">机</span>
        <div>
          <strong>本机用户</strong>
          <span className="settings-sub">本地单用户</span>
        </div>
      </div>
      <Field label="昵称" hint="仅本机显示">
        <input type="text" defaultValue="本机用户" disabled />
      </Field>
      <Field label="修改本机 PIN" hint="6-16 位数字">
        <input type="password" placeholder="输入新 PIN" disabled />
      </Field>
      <div className="settings-actions">
        <button type="button" className="ghost" disabled>清除本机数据</button>
      </div>
    </SettingsShell>
  )
}

export function ModelSettingsPage() {
  return (
    <SettingsShell
      eyebrow="MODEL"
      title="模型设置"
      description="LLM 提供商与密钥。API Key 不回显、不离开本机。"
    >
      <Field label="提供商">
        <select disabled>
          <option>OpenAI 兼容</option>
          <option>本地模型</option>
        </select>
      </Field>
      <Field label="Base URL">
        <input type="url" placeholder="https://api.openai.com/v1" disabled />
      </Field>
      <Field label="API Key" hint="password 类型，从不回填明文">
        <input type="password" placeholder="••••••••" disabled />
      </Field>
      <Field label="模型名">
        <input type="text" placeholder="gpt-4o-mini" disabled />
      </Field>
      <Field label="温度">
        <input type="number" step="0.1" min="0" max="2" defaultValue="0.7" disabled />
      </Field>
      <Field label="最大 Token">
        <input type="number" defaultValue="4096" disabled />
      </Field>
    </SettingsShell>
  )
}

export function LocalSettingsPage() {
  return (
    <SettingsShell
      eyebrow="LOCAL"
      title="本机设置"
      description="API 端口与采集安全基线。下限只读，不可在前端放宽。"
    >
      <Field label="API 端口">
        <input type="number" defaultValue="4173" disabled />
      </Field>
      <Field label="采集间隔下限" hint="≥1800ms，红线不可放宽">
        <input type="number" defaultValue="1800" disabled />
      </Field>
      <Field label="采集并发" hint="恒为 1">
        <input type="number" defaultValue="1" disabled />
      </Field>
      <Field label="数据目录">
        <input type="text" defaultValue="./data" disabled />
      </Field>
    </SettingsShell>
  )
}

export function ExtensionSettingsPage() {
  const extension = useQuery({
    queryKey: ['extension-status'],
    queryFn: ({ signal }) => fetchExtensionStatus(signal),
    refetchInterval: 4000,
  })
  const instances = extension.data?.instances ?? []
  const listBridge = [...instances].reverse().find((i) => i.role === 'list_bridge')
  const poolBridge = [...instances].reverse().find((i) => i.role === 'pool_bridge')

  return (
    <SettingsShell
      eyebrow="EXTENSION"
      title="扩展设置"
      description="浏览器扩展配对状态。配对令牌不回显。"
    >
      <div className="settings-bridge-row">
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
      <Field label="配对令牌" hint="已配对；令牌不回显，如需重置请清除本机数据">
        <input type="password" placeholder="••••••••" disabled />
      </Field>
      <Field label="配对码（粘贴）" hint="待后端接口接入">
        <input type="text" placeholder="输入配对码" disabled />
      </Field>
    </SettingsShell>
  )
}

export function ThemeSettingsPage({
  theme,
  onThemeChange,
}: {
  theme: Theme
  onThemeChange: (theme: Theme) => void
}) {
  return (
    <SettingsShell
      eyebrow="THEME"
      title="主题设置"
      description="界面主题与外观偏好。"
    >
      <ThemeControl theme={theme} onChange={onThemeChange} />
      <Field label="跟随系统" hint="待接入">
        <label className="settings-switch">
          <input type="checkbox" disabled />
          <span>随系统切换明暗</span>
        </label>
      </Field>
    </SettingsShell>
  )
}

export function KnowledgeSettingsPage() {
  return (
    <SettingsShell
      eyebrow="KNOWLEDGE"
      title="个人知识库设置"
      description="职业资产目录与抽取规则。未经确认的抽取内容不会成为事实。"
    >
      <Field label="知识库目录">
        <input type="text" defaultValue="./data/knowledge" disabled />
      </Field>
      <Field label="自动抽取" hint="待接入">
        <label className="settings-switch">
          <input type="checkbox" disabled />
          <span>导入时自动抽取事实</span>
        </label>
      </Field>
      <Field label="数据源管理">
        <input type="text" placeholder="暂无数据源" disabled />
      </Field>
    </SettingsShell>
  )
}

export function ResumeSettingsPage() {
  return (
    <SettingsShell
      eyebrow="RESUME"
      title="简历设置"
      description="默认简历版本与投递偏好。"
    >
      <Field label="默认简历版本">
        <select disabled>
          <option>主版本</option>
        </select>
      </Field>
      <Field label="投递偏好" hint="待接入">
        <input type="text" placeholder="暂无" disabled />
      </Field>
      <Field label="招呼语模板" hint="模板不写入事实文本">
        <textarea rows={3} placeholder="待接入" disabled />
      </Field>
    </SettingsShell>
  )
}

export function PrivacySettingsPage() {
  return (
    <SettingsShell
      eyebrow="PRIVACY"
      title="隐私设置"
      description="数据出境控制、日志等级与本机数据管理。聊天原文永不离开本机。"
    >
      <Field label="聊天不出本机" hint="恒开，红线不可关闭">
        <label className="settings-switch">
          <input type="checkbox" defaultChecked disabled />
          <span>聊天原文不进入第三方服务</span>
        </label>
      </Field>
      <Field label="日志等级">
        <select disabled>
          <option>WARNING</option>
          <option>INFO</option>
          <option>DEBUG</option>
        </select>
      </Field>
      <Field label="数据导出" hint="待接入">
        <button type="button" className="ghost" disabled>导出本机数据</button>
      </Field>
      <Field label="清除全部数据" hint="不可恢复">
        <button type="button" className="ghost" disabled>清除全部数据</button>
      </Field>
    </SettingsShell>
  )
}

/** 按路径渲染对应设置页。 */
export function renderSettingsPage(
  path: string,
  theme: Theme,
  onThemeChange: (t: Theme) => void,
): React.ReactNode {
  switch (path) {
    case '/settings/model':
      return <ModelSettingsPage />
    case '/settings/local':
      return <LocalSettingsPage />
    case '/settings/extension':
      return <ExtensionSettingsPage />
    case '/settings/theme':
      return <ThemeSettingsPage theme={theme} onThemeChange={onThemeChange} />
    case '/settings/knowledge':
      return <KnowledgeSettingsPage />
    case '/settings/resume':
      return <ResumeSettingsPage />
    case '/settings/privacy':
      return <PrivacySettingsPage />
    case '/settings':
    default:
      return <AccountSettingsPage />
  }
}

export { applyTheme }
