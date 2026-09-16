export type ExtensionStatus =
  | { paired: false }
  | {
      paired: true
      instance_id: string
      extension_version: string
      protocol_version: number
      connected_at: string
    }

export type CaptureRequest = {
  kind: 'list' | 'detail'
  query_url?: string
  max_items: number
  ext_ids?: string[]
  detail_limit: number
  delay_ms: number
}

export type BatchInfo = {
  id: string
  kind: string
  status: string
  stats: Record<string, unknown>
  risk_halted: boolean
  trigger: string
  started_at: string | null
  finished_at: string | null
}

export type RawJobItem = {
  id: string
  ext_id: string
  title: string | null
  company: string | null
  city: string | null
  district: string | null
  salary_text: string | null
  low_salary: number | null
  high_salary: number | null
  salary_unit: string
  exp_text: string | null
  exp_min_years: number | null
  exp_max_years: number | null
  degree: string | null
  degree_code: string | null
  list_at: string | null
  detail_at: string | null
  batch_id: string | null
}

export type CompanyItem = {
  id: string
  ext_company_id: string
  name: string | null
  sections: Record<string, unknown>
  updated_at: string
}

export type JobImportResult = {
  batch_id: string
  total: number
  created: number
  merged: number
  invalid: { index: number; reason: string }[]
}

export type EnrichState = 'pending' | 'detail_done' | 'done' | 'failed'

export type ShortlistItem = {
  id: string
  raw_job_id: string
  ext_id: string
  title: string | null
  company: string | null
  city: string | null
  salary_text: string | null
  status: 'confirmed' | 'removed'
  note: string | null
  enrich_state: EnrichState
  failure_reason?: string | null
  detail_at: string | null
  added_at: string | null
}

export type JobProfileJob = {
  id: string
  ext_id: string
  title: string | null
  company: string | null
  city: string | null
  district: string | null
  salary_text: string | null
  exp_text: string | null
  degree: string | null
  industry: string | null
  stage: string | null
  scale: string | null
  address: string | null
  boss_name: string | null
  active_time: string | null
  skill_tags: string[]
  jd_text: string | null
  detail_at: string | null
}

export type JobProfileCompany = {
  ext_company_id: string
  name: string | null
  sections: Record<string, unknown>
  updated_at: string | null
}

export type JobProfile = {
  job: JobProfileJob
  company: JobProfileCompany | null
}

export type ScreeningEntryStatus = 'screened' | 'candidate' | 'dismissed'

export type ScreeningEntryItem = {
  id: string
  raw_job_id: string
  ext_id: string
  title: string | null
  company: string | null
  city: string | null
  salary_text: string | null
  status: ScreeningEntryStatus
  entered_at: string
}

export type EnrichQueueStatus = {
  paused: boolean
  paused_reason: string | null
  running: { raw_job_id: string; ext_id: string; stage: string | null } | null
  pending: { raw_job_id: string; ext_id: string; title: string | null }[]
  blocked_reason?: string | null
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { message?: unknown }
    if (typeof data.message === 'string') return data.message
  } catch {
    // non-JSON error body
  }
  return `请求失败（${response.status}）`
}

export async function fetchExtensionStatus(signal?: AbortSignal): Promise<ExtensionStatus> {
  const response = await fetch('/api/extension/status', { signal })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ExtensionStatus
}

export async function createCapture(body: CaptureRequest): Promise<BatchInfo> {
  const response = await fetch('/api/captures', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as BatchInfo
}

export async function abortCapture(captureId: string): Promise<BatchInfo> {
  const response = await fetch(`/api/captures/${captureId}/abort`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: '控制台人工中止' }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as BatchInfo
}

export async function fetchRawJobs(signal?: AbortSignal, limit = 200): Promise<RawJobItem[]> {
  const response = await fetch(`/api/raw-jobs?limit=${limit}`, { signal })
  if (!response.ok) throw new Error(await parseError(response))
  const data = (await response.json()) as { items: RawJobItem[] }
  return data.items
}

/** Detail panel projection: JD full text + company snapshot (read-only, local). */
export async function fetchJobProfile(extId: string, signal?: AbortSignal): Promise<JobProfile> {
  const response = await fetch(`/api/raw-jobs/${encodeURIComponent(extId)}`, { signal })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as JobProfile
}

export async function fetchCompanies(signal?: AbortSignal): Promise<CompanyItem[]> {
  const response = await fetch('/api/companies?limit=20', { signal })
  if (!response.ok) throw new Error(await parseError(response))
  const data = (await response.json()) as { items: CompanyItem[] }
  return data.items
}

/** Upload an exporter JSON; the server upserts by (source, ext_id). */
export async function importJobs(file: File): Promise<JobImportResult> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/jobs/import', { method: 'POST', body })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as JobImportResult
}

export async function fetchShortlist(signal?: AbortSignal): Promise<ShortlistItem[]> {
  const response = await fetch('/api/shortlist', { signal })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ShortlistItem[]
}

export async function addToPool(extId: string): Promise<ShortlistItem> {
  const response = await fetch('/api/shortlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ext_id: extId }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ShortlistItem
}

export async function removeFromPool(shortlistId: string): Promise<ShortlistItem> {
  const response = await fetch(`/api/shortlist/${shortlistId}/remove`, { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ShortlistItem
}

export async function fetchEnrichQueue(signal?: AbortSignal): Promise<EnrichQueueStatus> {
  const response = await fetch('/api/enrich/queue', { signal })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as EnrichQueueStatus
}

/** Human acknowledgement after a risk halt; never called automatically. */
export async function resumeEnrich(): Promise<EnrichQueueStatus> {
  const response = await fetch('/api/enrich/resume', { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as EnrichQueueStatus
}

// ------------------------------------------------------------------ screening
// 筛选池：岗位池补全完成自动流入；进入候选区只由人工点击触发（ARCH-GOV-002）。

export async function fetchScreeningEntries(
  status: 'screened' | 'candidate' = 'screened',
  signal?: AbortSignal,
): Promise<ScreeningEntryItem[]> {
  const response = await fetch(`/api/screening-entries?status=${status}`, { signal })
  if (!response.ok) throw new Error(await parseError(response))
  const data = (await response.json()) as { items: ScreeningEntryItem[] }
  return data.items
}

/** 人工确认进入候选区（screened → candidate）。 */
export async function promoteScreeningEntry(id: string): Promise<ScreeningEntryItem> {
  const response = await fetch(`/api/screening-entries/${id}/promote`, { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ScreeningEntryItem
}

/** 忽略该岗位（screened → dismissed，终态）。 */
export async function dismissScreeningEntry(id: string): Promise<ScreeningEntryItem> {
  const response = await fetch(`/api/screening-entries/${id}/dismiss`, { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ScreeningEntryItem
}

/** 候选区退回筛选池（candidate → screened）。 */
export async function revertScreeningEntry(id: string): Promise<ScreeningEntryItem> {
  const response = await fetch(`/api/screening-entries/${id}/revert`, { method: 'POST' })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as ScreeningEntryItem
}
