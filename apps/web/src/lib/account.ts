export type Account = {
  id: string
  email: string
  role: 'seeker' | 'recruiter'
  is_admin: boolean
  display_name: string
}

export type Profile = {
  display_name: string
  basic: Record<string, unknown>
  education: Record<string, unknown>
  job_preference: Record<string, unknown>
  onboarding_step: 'entry' | 'basic' | 'education' | 'job-preference' | 'complete'
}

function csrf(): string {
  const entry = document.cookie.split('; ').find((part) => part.startsWith('jobos_csrf='))
  return entry ? decodeURIComponent(entry.slice('jobos_csrf='.length)) : ''
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init.method && init.method !== 'GET' ? { 'X-CSRF-Token': csrf() } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as { message?: string; code?: string }
    const error = new Error(problem.message || `请求失败 (${response.status})`)
    Object.assign(error, { status: response.status, code: problem.code })
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function getMe(): Promise<Account> { return api('/me') }
export function login(email: string, password: string): Promise<Account> {
  return api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
}
export function register(email: string, password: string, invite_token: string): Promise<void> {
  return api('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, invite_token }) })
}
export function logout(): Promise<void> { return api('/auth/logout', { method: 'POST' }) }
export function deleteAccount(): Promise<void> { return api('/me', { method: 'DELETE' }) }
export function getProfile(): Promise<Profile> { return api('/me/profile') }
export function saveProfile(profile: Profile): Promise<Profile> {
  return api('/me/profile', { method: 'PUT', body: JSON.stringify(profile) })
}
export function uploadResume(file: File): Promise<{ id: string; status: 'stored'; filename: string }> {
  const body = new FormData()
  body.set('file', file)
  return api('/me/resumes', { method: 'POST', body })
}
