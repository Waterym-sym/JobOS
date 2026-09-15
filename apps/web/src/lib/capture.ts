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
  salary_text: string | null
  exp_text: string | null
  degree: string | null
  list_at: string | null
  detail_at: string | null
  batch_id: string | null
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

export async function fetchRawJobs(signal?: AbortSignal): Promise<RawJobItem[]> {
  const response = await fetch('/api/raw-jobs?limit=20', { signal })
  if (!response.ok) throw new Error(await parseError(response))
  const data = (await response.json()) as { items: RawJobItem[] }
  return data.items
}
