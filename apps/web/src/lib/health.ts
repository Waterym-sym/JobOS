export type HealthStatus = {
  service: string
  status: 'ok'
  time: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthStatus> {
  const response = await fetch('/api/healthz', { signal })
  if (!response.ok) {
    throw new Error(`Health check failed with ${response.status}`)
  }
  return response.json() as Promise<HealthStatus>
}
