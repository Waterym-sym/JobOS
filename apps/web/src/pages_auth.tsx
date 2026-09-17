import { useState } from 'react'

/**
 * 本机 PIN 锁屏：单用户本地系统，无云端账号。
 * 首次使用设置 PIN 与昵称；之后输入 PIN 解锁。
 * 数据仅存本机 localStorage，不进后端、不进日志。
 */

const PIN_KEY = 'jobos.pin'
const NICK_KEY = 'jobos.nickname'

export function hasLocalPin(): boolean {
  try {
    return Boolean(window.localStorage.getItem(PIN_KEY))
  } catch {
    return false
  }
}

export function getNickname(): string {
  try {
    return window.localStorage.getItem(NICK_KEY) ?? '本机用户'
  } catch {
    return '本机用户'
  }
}

export function isUnlocked(): boolean {
  try {
    return window.sessionStorage.getItem('jobos.unlocked') === '1'
  } catch {
    return false
  }
}

function setUnlocked() {
  try {
    window.sessionStorage.setItem('jobos.unlocked', '1')
  } catch {
    /* ignore */
  }
}

export function clearLocalIdentity() {
  try {
    window.localStorage.removeItem(PIN_KEY)
    window.localStorage.removeItem(NICK_KEY)
    window.sessionStorage.removeItem('jobos.unlocked')
  } catch {
    /* ignore */
  }
}

export function LoginPage({ onUnlock }: { onUnlock: () => void }) {
  const needsSetup = !hasLocalPin()
  const [step, setStep] = useState<'setup' | 'unlock'>(needsSetup ? 'setup' : 'unlock')
  const [nickname, setNickname] = useState('')
  const [pin, setPin] = useState('')
  const [pinConfirm, setPinConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSetup = () => {
    const nick = nickname.trim() || '本机用户'
    if (pin.length < 6) {
      setError('PIN 至少 6 位')
      return
    }
    if (pin !== pinConfirm) {
      setError('两次输入的 PIN 不一致')
      return
    }
    try {
      window.localStorage.setItem(PIN_KEY, pin)
      window.localStorage.setItem(NICK_KEY, nick)
    } catch {
      setError('无法写入本机存储，请检查浏览器隐私设置')
      return
    }
    setUnlocked()
    onUnlock()
  }

  const handleUnlock = () => {
    const stored = (() => {
      try {
        return window.localStorage.getItem(PIN_KEY)
      } catch {
        return null
      }
    })()
    if (pin === stored) {
      setUnlocked()
      onUnlock()
    } else {
      setError('PIN 不正确')
    }
  }

  const handleReset = () => {
    clearLocalIdentity()
    setPin('')
    setPinConfirm('')
    setError(null)
    setStep('setup')
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">JO</span>
          <div>
            <h1>JobOS</h1>
            <p>本机求职闭环 · 数据留在本机</p>
          </div>
        </div>

        {step === 'setup' ? (
          <>
            <h2>首次使用：设置本机身份</h2>
            <p className="auth-hint">
              此 PIN 仅用于解锁本机 JobOS，不会上传到任何服务器。
            </p>

            <label className="auth-field">
              <span>昵称</span>
              <input
                type="text"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="本机用户"
                maxLength={20}
                autoFocus
              />
            </label>

            <label className="auth-field">
              <span>设置 PIN（6-16 位）</span>
              <input
                type="password"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 16))}
                placeholder="至少 6 位数字"
                inputMode="numeric"
              />
            </label>

            <label className="auth-field">
              <span>确认 PIN</span>
              <input
                type="password"
                value={pinConfirm}
                onChange={(e) => setPinConfirm(e.target.value.replace(/\D/g, '').slice(0, 16))}
                placeholder="再次输入"
                inputMode="numeric"
              />
            </label>

            {error ? <p className="auth-error">{error}</p> : null}

            <button type="button" className="auth-submit" onClick={handleSetup}>
              设置并进入
            </button>
          </>
        ) : (
          <>
            <h2>解锁 JobOS</h2>
            <p className="auth-hint">欢迎回来，{getNickname()}。请输入本机 PIN。</p>

            <label className="auth-field">
              <span>本机 PIN</span>
              <input
                type="password"
                value={pin}
                onChange={(e) => {
                  setPin(e.target.value.replace(/\D/g, '').slice(0, 16))
                  setError(null)
                }}
                placeholder="输入 PIN"
                inputMode="numeric"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleUnlock()
                }}
              />
            </label>

            {error ? <p className="auth-error">{error}</p> : null}

            <button type="button" className="auth-submit" onClick={handleUnlock}>
              解锁
            </button>

            <div className="auth-reset">
              <button type="button" className="auth-link" onClick={handleReset}>
                忘记 PIN？清除本机数据重新设置
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
