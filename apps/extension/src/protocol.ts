export const PROTOCOL_VERSION = 1 as const
export const DEFAULT_WS_URL = 'ws://127.0.0.1:8788/ws' as const

export type AuthPing = {
  v: 1
  kind: 'handshake'
  id: string
  type: 'auth_ping'
  payload: {
    token: string
    extension_version: string
    protocol_version: 1
  }
}

export function uuid7(now = Date.now()): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)

  let timestamp = BigInt(now)
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = Number(timestamp & 0xffn)
    timestamp >>= 8n
  }

  bytes[6] = (bytes[6]! & 0x0f) | 0x70
  bytes[8] = (bytes[8]! & 0x3f) | 0x80

  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function buildAuthPing(token: string, extensionVersion: string): AuthPing {
  return {
    v: PROTOCOL_VERSION,
    kind: 'handshake',
    id: uuid7(),
    type: 'auth_ping',
    payload: {
      token,
      extension_version: extensionVersion,
      protocol_version: PROTOCOL_VERSION,
    },
  }
}
