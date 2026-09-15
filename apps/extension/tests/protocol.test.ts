import { describe, expect, it } from 'vitest'

import { buildAuthPing, DEFAULT_WS_URL, uuid7 } from '../src/protocol'

describe('pairing protocol', () => {
  it('builds the client-first auth handshake', () => {
    const request = buildAuthPing('0123456789abcdef', '0.1.0')

    expect(request).toMatchObject({
      v: 1,
      kind: 'handshake',
      type: 'auth_ping',
      payload: {
        token: '0123456789abcdef',
        extension_version: '0.1.0',
        protocol_version: 1,
      },
    })
  })

  it('creates UUIDv7 message identifiers', () => {
    const id = uuid7(1_700_000_000_000)

    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it('pins the gateway to the loopback endpoint', () => {
    expect(DEFAULT_WS_URL).toBe('ws://127.0.0.1:8788/ws')
  })
})
