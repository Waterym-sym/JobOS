import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchHealth } from './health'

describe('fetchHealth', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns the local API status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ service: 'api', status: 'ok', time: '2026-09-15T00:00:00Z' }),
          { status: 200 },
        ),
      ),
    )

    await expect(fetchHealth()).resolves.toMatchObject({ service: 'api', status: 'ok' })
  })

  it('surfaces an unavailable API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))
    await expect(fetchHealth()).rejects.toThrow('503')
  })
})
