import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { getProfile, saveProfile, uploadResume, type Profile } from './lib/account'
import './ported/tokens.css'
import './ported/Onboarding.css'

type Step = Profile['onboarding_step'] | 'uploading' | 'upload-success'

export default function OnboardingFlow({ onComplete, onBackToLogin }: {
  onComplete: () => void
  onBackToLogin: () => void
}) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [step, setStep] = useState<Step>('entry')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const [basic, setBasic] = useState({ name: '', birth: '', gender: '', identity: '', experience: '' })
  const [education, setEducation] = useState({ level: '', school: '', major: '', dates: '' })
  const [preference, setPreference] = useState({ positions: '', city: '', email: '' })

  useEffect(() => {
    let active = true
    void getProfile().then((value) => {
      if (!active) return
      setProfile(value)
      setStep(value.onboarding_step)
      setBasic({ name: String(value.basic.name ?? ''), birth: String(value.basic.birth ?? ''),
        gender: String(value.basic.gender ?? ''), identity: String(value.basic.identity ?? ''),
        experience: String(value.basic.experience ?? '') })
      setEducation({ level: String(value.education.level ?? ''), school: String(value.education.school ?? ''),
        major: String(value.education.major ?? ''), dates: String(value.education.dates ?? '') })
      setPreference({ positions: String(value.job_preference.positions ?? ''),
        city: String(value.job_preference.city ?? ''), email: String(value.job_preference.email ?? '') })
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法加载入门资料') })
    return () => { active = false }
  }, [])

  async function advance(next: Profile['onboarding_step']) {
    if (!profile) return
    setSaving(true)
    setError('')
    try {
      const value = await saveProfile({ ...profile, basic, education,
        job_preference: preference, onboarding_step: next })
      setProfile(value)
      setStep(next)
      if (next === 'complete') onComplete()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试')
    } finally { setSaving(false) }
  }

  async function upload(file: File | undefined) {
    if (!file) return
    setStep('uploading')
    setError('')
    try {
      await uploadResume(file)
      setStep('upload-success')
      window.setTimeout(() => { void advance('job-preference') }, 900)
    } catch (cause) {
      setStep('entry')
      setError(cause instanceof Error ? cause.message : '简历上传失败')
    }
  }

  if (!profile || step === 'complete') return null
  const pick = () => fileInput.current?.click()
  const input = <input ref={fileInput} type="file" accept=".pdf,.docx" hidden
    onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = '' }} />
  const banner = <div className="onboarding-banner"><span className="onboarding-banner__left">
    <span className="onboarding-banner__icon">◉</span><span className="onboarding-banner__text">已有简历？可上传 PDF/DOCX 原件，解析功能将另行提示。</span>
    </span><button type="button" className="onboarding-banner__btn" onClick={pick}>去上传</button></div>
  const progress = (current: number) => <div className="onboarding-progress">
    <div className="onboarding-progress__track"><div className="onboarding-progress__fill" style={{ width: `${current / 3 * 100}%` }} /></div>
    <span className="onboarding-progress__badge">{current}/3</span></div>
  const nav = (back: Step, next: Profile['onboarding_step'], label = '下一步') => <div className="onboarding-nav">
    <button type="button" className="onboarding-nav__back" onClick={() => setStep(back)}>←</button>
    <button type="button" className="onboarding-nav__next" disabled={saving}
      onClick={() => void advance(next)}>{saving ? '保存中…' : label}</button></div>

  let content: React.ReactNode
  if (step === 'entry') {
    content = <div className="onboarding-shell onboarding-shell--entry" role="dialog" aria-modal="true">
      {input}<h1 className="onboarding-entry__title">轻松找到理想好工作！</h1>
      <p className="onboarding-entry__subtitle">从简历或空白资料开始，逐步建立你的求职档案</p>
      <div className="onboarding-entry__cards">
        <button type="button" className="onboarding-entry__card" onClick={pick}>
          <span className="onboarding-entry__badge">⚛ 极速求职</span>
          <div className="onboarding-entry__card-icon"><svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true"><rect x="12" y="8" width="40" height="48" rx="6" fill="#1677ff" /><circle cx="32" cy="26" r="8" fill="#fff" /><rect x="22" y="38" width="20" height="4" rx="2" fill="#fff" opacity=".7" /></svg></div>
          <div className="onboarding-entry__card-title">我有简历 ›</div>
          <div className="onboarding-entry__card-desc">上传并私有保存简历原件</div>
        </button>
        <button type="button" className="onboarding-entry__card" onClick={() => void advance('basic')}>
          <div className="onboarding-entry__card-icon"><svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true"><rect x="14" y="10" width="36" height="44" rx="5" fill="#4e5969" /><path d="M22 22h20M22 30h16M22 38h12" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg></div>
          <div className="onboarding-entry__card-title">暂无简历 ›</div>
          <div className="onboarding-entry__card-desc">轻松几步创建求职档案</div>
        </button>
      </div><button type="button" className="onboarding-entry__back" onClick={onBackToLogin}>← 返回登录</button>
    </div>
  } else if (step === 'uploading' || step === 'upload-success') {
    content = <div className="onboarding-shell onboarding-shell--compact" role="dialog" aria-modal="true">
      <div className="onboarding-upload__success-icon">{step === 'uploading' ? '↑' : '✓'}</div>
      <h2 className="onboarding-upload__title">{step === 'uploading' ? '简历上传中' : '上传成功！'}</h2>
      <p className="onboarding-upload__desc">{step === 'uploading' ? '文件正在保存到你的私有空间' : '原件已保存；尚未完成 AI 解析'}</p>
      <div className="onboarding-upload__bar"><div className="onboarding-upload__bar-fill" style={{ width: step === 'uploading' ? '35%' : '100%' }} /></div>
    </div>
  } else if (step === 'basic') {
    content = <div className="onboarding-shell onboarding-shell--wide" role="dialog" aria-modal="true">
      {input}{banner}{progress(1)}<div className="onboarding-form"><div className="onboarding-form__body">
        <h2 className="onboarding-form__title">完善你的基本信息</h2>
        <p className="onboarding-form__subtitle">所有字段从空白开始，由你确认后保存</p>
        <div className="onboarding-gender">{(['male', 'female'] as const).map((item) => <button key={item} type="button" className={`onboarding-gender__btn ${basic.gender === item ? 'onboarding-gender__btn--active' : ''}`} onClick={() => setBasic({ ...basic, gender: item })}><span className="onboarding-gender__avatar">{item === 'male' ? '👨' : '👩'}</span>{item === 'male' ? '我是男生' : '我是女生'}</button>)}</div>
        <label className="onboarding-field"><span className="onboarding-field__label">你的姓名</span><div className="onboarding-input-wrap"><input className="onboarding-input" value={basic.name} maxLength={20} onChange={(e) => setBasic({ ...basic, name: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">出生年月</span><div className="onboarding-input-wrap"><input className="onboarding-input" type="month" value={basic.birth} onChange={(e) => setBasic({ ...basic, birth: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">当前身份</span><div className="onboarding-input-wrap"><select className="onboarding-select" value={basic.identity} onChange={(e) => setBasic({ ...basic, identity: e.target.value })}><option value="">请选择</option><option value="student">在校生</option><option value="professional">职场人</option></select></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">工作经验</span><div className="onboarding-input-wrap"><select className="onboarding-select" value={basic.experience} onChange={(e) => setBasic({ ...basic, experience: e.target.value })}><option value="">请选择</option><option value="0">应届生</option><option value="1-3">1–3 年</option><option value="3-5">3–5 年</option><option value="5+">5 年以上</option></select></div></label>
      </div>{nav('entry', 'education')}</div>
    </div>
  } else if (step === 'education') {
    content = <div className="onboarding-shell onboarding-shell--wide" role="dialog" aria-modal="true">
      {input}{banner}{progress(2)}<div className="onboarding-form"><div className="onboarding-form__body">
        <h2 className="onboarding-form__title">完善你的教育经历</h2><p className="onboarding-form__subtitle">请只填写真实且由你确认的信息</p>
        <div className="onboarding-field"><span className="onboarding-field__label">最高学历</span><div className="onboarding-edu-levels">{['博士', '硕士', '本科', '其他'].map((item) => <button key={item} type="button" className={`onboarding-edu-levels__btn ${education.level === item ? 'onboarding-edu-levels__btn--active' : ''}`} onClick={() => setEducation({ ...education, level: item })}>{item}</button>)}</div></div>
        <label className="onboarding-field"><span className="onboarding-field__label">学校名称</span><div className="onboarding-input-wrap"><input className="onboarding-input" value={education.school} onChange={(e) => setEducation({ ...education, school: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">所学专业</span><div className="onboarding-input-wrap"><input className="onboarding-input" value={education.major} onChange={(e) => setEducation({ ...education, major: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">起止时间</span><div className="onboarding-input-wrap"><input className="onboarding-input" placeholder="例如 2021-09 至 2025-06" value={education.dates} onChange={(e) => setEducation({ ...education, dates: e.target.value })} /></div></label>
      </div>{nav('basic', 'job-preference')}</div>
    </div>
  } else {
    content = <div className="onboarding-shell onboarding-shell--wide" role="dialog" aria-modal="true">
      <div className="onboarding-job__header"><span className="onboarding-job__header-icon">◉</span> AI 助力轻松找到好工作！</div>
      <div className="onboarding-form"><div className="onboarding-form__body">
        <h2 className="onboarding-form__title">你想找什么工作？</h2><p className="onboarding-form__subtitle">你的求职意向只属于当前账号</p>
        <label className="onboarding-field"><span className="onboarding-field__label">意向职位</span><div className="onboarding-input-wrap"><input className="onboarding-input" value={preference.positions} onChange={(e) => setPreference({ ...preference, positions: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">意向城市</span><div className="onboarding-input-wrap"><input className="onboarding-input" value={preference.city} onChange={(e) => setPreference({ ...preference, city: e.target.value })} /></div></label>
        <label className="onboarding-field"><span className="onboarding-field__label">常用邮箱</span><div className="onboarding-input-wrap"><input className="onboarding-input" type="email" value={preference.email} onChange={(e) => setPreference({ ...preference, email: e.target.value })} /></div></label>
      </div>{nav('education', 'complete', '进入 JobOS')}</div>
    </div>
  }
  return createPortal(<div className="onboarding-root" role="presentation">
    <div className="onboarding-root__backdrop" aria-hidden="true" />{content}
    {error ? <div className="onboarding-error" role="alert">{error}</div> : null}
  </div>, document.body)
}
