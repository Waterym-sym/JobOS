import { useState } from 'react'

import { deleteAccount, login, logout, register, type Account } from './lib/account'
import './ported/tokens.css'
import './ported/LoginPage.css'
import './ported/UserPage.css'
import './ported/AccountSettingsPage.css'
import './ported/dialogs.css'

export function AccountLoginPage({ onLogin }: { onLogin: (account: Account) => void }) {
  const [role, setRole] = useState<'seeker' | 'recruiter'>('seeker')
  const [registering, setRegistering] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError('')
    try {
      if (registering) {
        await register(email, password, invite)
      }
      const account = await login(email, password)
      if (account.role !== role) {
        await logout()
        setError(`该账号属于${account.role === 'seeker' ? '求职者' : '招聘者'}，请切换上方角色`)
        return
      }
      onLogin(account)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '登录失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-page__card" onSubmit={(event) => { event.preventDefault(); void submit() }}>
        <div className="login-page__role-switch" role="tablist" aria-label="账号角色">
          <button type="button" role="tab" aria-selected={role === 'seeker'}
            className={`login-page__role-btn ${role === 'seeker' ? 'login-page__role-btn--active' : ''}`}
            onClick={() => setRole('seeker')}>我要找工作</button>
          <button type="button" role="tab" aria-selected={role === 'recruiter'}
            className={`login-page__role-btn ${role === 'recruiter' ? 'login-page__role-btn--active' : ''}`}
            onClick={() => setRole('recruiter')}>我要招人</button>
        </div>
        <h1 className="login-page__title">邮箱{registering ? '注册' : '登录'}</h1>
        <div className="login-page__field">
          <div className="login-page__phone-input">
            <input type="email" autoComplete="email" required aria-label="邮箱" placeholder="请输入邮箱"
              value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
        </div>
        <div className="login-page__field">
          <div className="login-page__code-input">
            <input type="password" autoComplete={registering ? 'new-password' : 'current-password'}
              required minLength={12} aria-label="密码" placeholder="请输入密码（至少 12 位）"
              value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
        </div>
        {registering ? (
          <div className="login-page__field">
            <div className="login-page__code-input">
              <input type="text" required aria-label="邀请码" placeholder="请输入管理员邀请码"
                value={invite} onChange={(event) => setInvite(event.target.value)} />
            </div>
          </div>
        ) : null}
        {error ? <p className="login-page__mock-hint" role="alert" style={{ color: '#d4380d' }}>{error}</p> : null}
        <button type="submit" className="login-page__submit" disabled={busy}>
          {busy ? '请稍候…' : registering ? '注册并登录' : '立即登录'}
        </button>
        <p className="login-page__mock-hint">{registering ? '仅接受管理员签发的一次性邀请' : '使用受邀请的 JobOS 账号登录'}</p>
        <div className="login-page__alt">
          <button type="button" className="login-page__alt-btn" onClick={() => { setRegistering(!registering); setError('') }}>
            {registering ? '已有账号？返回登录' : '持邀请码注册'}
          </button>
          <button type="button" className="login-page__alt-btn" disabled title="尚未接入第三方登录">第三方登录暂未开放</button>
        </div>
        <p className="login-page__agreement">登录即表示同意 JobOS 的使用规则；隐私与账号删除以当前部署的正式告知为准。</p>
      </form>
    </div>
  )
}

function Chevron() {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
    <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}

export function AccountSettings({ account, onAccountChange, onLogout }: {
  account: Account
  onAccountChange: (account: Account) => void
  onLogout: () => void
}) {
  const [dialog, setDialog] = useState<'profile' | 'logout' | 'delete' | null>(null)
  const [name, setName] = useState(account.display_name)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function confirm() {
    setBusy(true)
    setError('')
    try {
      if (dialog === 'logout') {
        await logout()
        onLogout()
      } else if (dialog === 'delete') {
        await deleteAccount()
        onLogout()
      } else if (dialog === 'profile') {
        const { getProfile, saveProfile } = await import('./lib/account')
        const profile = await getProfile()
        const saved = await saveProfile({ ...profile, display_name: name })
        onAccountChange({ ...account, display_name: saved.display_name })
      }
      setDialog(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return <div className="user-page account-settings-page">
    <h1 className="user-page__title">账号设置</h1>
    <div className="user-page__content account-settings-page__stack">
      <button type="button" className="account-settings-page__profile-card" onClick={() => setDialog('profile')}>
        <span className="account-settings-page__avatar">{account.display_name.slice(0, 1) || 'J'}</span>
        <span className="account-settings-page__profile-info">
          <span className="account-settings-page__name">{account.display_name}</span>
          <span className="account-settings-page__phone">{account.email}</span>
        </span>
        <span className="account-settings-page__chevron"><Chevron /></span>
      </button>
      <div className="account-settings-page__menu-card">
        {['联系我们', '用户反馈', '用户协议', '隐私政策', '关于 JobOS'].map((label) => (
          <button key={label} type="button" className="account-settings-page__menu-item" disabled title="本期尚未开放">
            <span className="account-settings-page__menu-icon" aria-hidden="true">◇</span>
            <span className="account-settings-page__menu-label">{label}</span>
            <span className="account-settings-page__chevron"><Chevron /></span>
          </button>
        ))}
        <button type="button" className="account-settings-page__menu-item" onClick={() => setDialog('delete')}>
          <span className="account-settings-page__menu-icon" aria-hidden="true">◇</span>
          <span className="account-settings-page__menu-label">注销账号</span>
          <span className="account-settings-page__delete">注销</span>
        </button>
      </div>
      <button type="button" className="account-settings-page__logout-card" onClick={() => setDialog('logout')}>退出登录</button>
    </div>
    {dialog ? <div className="account-dialog-backdrop" role="presentation">
      <div className="account-dialog" role="dialog" aria-modal="true" aria-label={dialog === 'profile' ? '编辑个人信息' : dialog === 'delete' ? '注销账号' : '退出登录'}>
        <h2>{dialog === 'profile' ? '编辑个人信息' : dialog === 'delete' ? '确认注销账号？' : '退出登录'}</h2>
        {dialog === 'profile' ? <label>显示名称<input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} /></label>
          : <p>{dialog === 'delete' ? '该账号的私有资料与简历文件将被删除，此操作不可恢复。' : '确定要退出当前账号吗？'}</p>}
        {error ? <p role="alert" className="account-dialog__error">{error}</p> : null}
        <div className="account-dialog__actions">
          <button type="button" onClick={() => { setDialog(null); setError('') }}>取消</button>
          <button type="button" disabled={busy} onClick={() => void confirm()}>{busy ? '请稍候…' : dialog === 'delete' ? '确认注销' : dialog === 'profile' ? '保存' : '退出登录'}</button>
        </div>
      </div>
    </div> : null}
  </div>
}
