/**
 * Local-only WebSocket client (protocol #21 §2/§4).
 *
 * Owns the single paired connection: handshake, command dispatch and the
 * receipt/event envelopes the server persists. Command execution lives in
 * commands.ts.
 */

import { buildAuthPing, DEFAULT_WS_URL } from './protocol'

// A closed socket (server restart, network hiccup) must not leave the bridge
// offline until the user reloads: retry with a capped backoff.
const RECONNECT_MIN_MS = 3_000
const RECONNECT_MAX_MS = 30_000

export type CommandEnvelope = {
  v: 1
  kind: 'command'
  id: string
  type: string
  command_id?: string
  capture_id?: string | null
  payload: Record<string, unknown>
}

export type CommandContext = {
  captureId: string | null
  commandId: string | null
}

type GatewayMessage = {
  type?: unknown
  code?: unknown
  payload?: { supported?: unknown }
  kind?: unknown
  id?: unknown
  command_id?: unknown
  capture_id?: unknown
}

type PairingConfig = {
  ws_url?: string
  pairing_token?: string
}

type CommandHandler = (command: CommandEnvelope) => void

let activeSocket: WebSocket | undefined
let commandHandler: CommandHandler | undefined
let reconnectTimer: ReturnType<typeof setTimeout> | undefined
let reconnectDelayMs = RECONNECT_MIN_MS

export function setCommandHandler(handler: CommandHandler): void {
  commandHandler = handler
}

export function isConnected(): boolean {
  return activeSocket?.readyState === WebSocket.OPEN
}

export async function setPairingStatus(status: string, detail: string): Promise<void> {
  await chrome.storage.local.set({ pairing_status: status, pairing_detail: detail })
}

function closeActiveSocket(): void {
  if (activeSocket) {
    activeSocket.close(1000, 'configuration_changed')
    activeSocket = undefined
  }
}

function scheduleReconnect(): void {
  if (reconnectTimer !== undefined) return
  const delay = reconnectDelayMs
  reconnectDelayMs = Math.min(reconnectDelayMs * 2, RECONNECT_MAX_MS)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = undefined
    void connectOnce()
  }, delay)
}

export function cancelReconnect(): void {
  if (reconnectTimer !== undefined) {
    clearTimeout(reconnectTimer)
    reconnectTimer = undefined
  }
}

export function sendMessage(message: Record<string, unknown>): boolean {
  if (!isConnected()) return false
  activeSocket?.send(JSON.stringify(message))
  return true
}

export function sendReceipt(
  type: 'command.started' | 'command.progress' | 'command.completed' | 'command.error',
  payload: Record<string, unknown>,
  ctx: CommandContext,
): void {
  sendMessage({
    v: 1,
    kind: 'receipt',
    id: crypto.randomUUID(),
    type,
    command_id: ctx.commandId,
    capture_id: ctx.captureId,
    payload,
  })
}

export function sendEvent(
  type: 'capture.phase' | 'capture.completed' | 'capture.error' | 'job.updated' | 'company.updated',
  payload: Record<string, unknown>,
  ctx: CommandContext,
): void {
  sendMessage({
    v: 1,
    kind: 'event',
    id: crypto.randomUUID(),
    type,
    capture_id: ctx.captureId,
    command_id: ctx.commandId,
    payload,
  })
}

export async function connectOnce(): Promise<void> {
  cancelReconnect()
  closeActiveSocket()
  const config = (await chrome.storage.local.get([
    'ws_url',
    'pairing_token',
  ])) as PairingConfig
  const wsUrl = config.ws_url ?? DEFAULT_WS_URL
  const token = config.pairing_token?.trim()

  if (wsUrl !== DEFAULT_WS_URL || !token || token.length < 16) {
    await setPairingStatus('not_configured', '请在扩展选项中保存本机配对令牌。')
    return
  }

  const socket = new WebSocket(wsUrl)
  activeSocket = socket
  await setPairingStatus('connecting', '正在连接本机 JobOS。')

  socket.addEventListener('open', () => {
    reconnectDelayMs = RECONNECT_MIN_MS
    socket.send(JSON.stringify(buildAuthPing(token, chrome.runtime.getManifest().version)))
  })

  socket.addEventListener('message', (event) => {
    if (typeof event.data !== 'string') return

    let message: GatewayMessage
    try {
      message = JSON.parse(event.data) as GatewayMessage
    } catch {
      void setPairingStatus('error', '本机服务返回了无法识别的响应。')
      socket.close(1002, 'invalid_response')
      return
    }

    if (message.kind === 'command') {
      const command = message as unknown as CommandEnvelope
      if (typeof command.type === 'string' && typeof command.id === 'string') {
        commandHandler?.(command)
      }
      return
    }
    if (message.type === 'auth_pong' && message.payload?.supported === true) {
      void setPairingStatus('paired', '已与本机 JobOS 安全配对。')
      return
    }
    if (message.type === 'auth_pong' && message.payload?.supported === false) {
      void setPairingStatus('version_mismatch', '扩展协议版本不受本机服务支持。')
      return
    }
    if (typeof message.code === 'string') {
      const detail =
        message.code === 'PAIRING_TOKEN_INVALID'
          ? '配对令牌无效，请重新输入。'
          : '本机服务拒绝了连接。'
      void setPairingStatus('rejected', detail)
    }
  })

  socket.addEventListener('error', () => {
    void setPairingStatus('unreachable', '无法连接本机 JobOS，请确认服务已启动。')
  })

  socket.addEventListener('close', () => {
    if (activeSocket === socket) activeSocket = undefined
    // Reconnect on our own: a restarted local service must not require a
    // manual extension reload.
    scheduleReconnect()
  })
}