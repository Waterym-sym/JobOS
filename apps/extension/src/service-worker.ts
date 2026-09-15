import { buildAuthPing, DEFAULT_WS_URL } from './protocol'

type PairingConfig = {
  ws_url?: string
  pairing_token?: string
}

type GatewayMessage = {
  type?: unknown
  code?: unknown
  payload?: { supported?: unknown }
}

let activeSocket: WebSocket | undefined

async function setPairingStatus(status: string, detail: string): Promise<void> {
  await chrome.storage.local.set({ pairing_status: status, pairing_detail: detail })
}

function closeActiveSocket(): void {
  if (activeSocket) {
    activeSocket.close(1000, 'configuration_changed')
    activeSocket = undefined
  }
}

async function connectOnce(): Promise<void> {
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
  })
}

chrome.runtime.onInstalled.addListener(() => {
  void chrome.storage.local
    .get('ws_url')
    .then((stored) => {
      if (stored.ws_url === undefined) return chrome.storage.local.set({ ws_url: DEFAULT_WS_URL })
      return undefined
    })
    .then(connectOnce)
})

chrome.runtime.onStartup.addListener(() => {
  void connectOnce()
})

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && (changes.ws_url || changes.pairing_token)) {
    void connectOnce()
  }
})

void connectOnce()
