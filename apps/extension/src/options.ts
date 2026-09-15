import { DEFAULT_WS_URL } from './protocol'

const form = document.querySelector<HTMLFormElement>('#pairing-form')
const tokenInput = document.querySelector<HTMLInputElement>('#pairing-token')
const endpoint = document.querySelector<HTMLElement>('#endpoint')
const status = document.querySelector<HTMLElement>('#status')

if (!form || !tokenInput || !endpoint || !status) {
  throw new Error('Pairing options page is incomplete')
}

const statusElement = status
endpoint.textContent = DEFAULT_WS_URL

const statusLabels: Record<string, string> = {
  not_configured: '等待配置',
  connecting: '正在连接',
  paired: '已配对',
  version_mismatch: '版本不兼容',
  rejected: '配对失败',
  unreachable: '服务未连接',
  error: '响应异常',
}

async function refreshStatus(): Promise<void> {
  const stored = await chrome.storage.local.get(['pairing_status', 'pairing_detail'])
  const state = typeof stored.pairing_status === 'string' ? stored.pairing_status : 'not_configured'
  const detail =
    typeof stored.pairing_detail === 'string'
      ? stored.pairing_detail
      : '输入桌面端生成的配对令牌。'
  statusElement.dataset.state = state
  statusElement.textContent = `${statusLabels[state] ?? '未知状态'} · ${detail}`
}

form.addEventListener('submit', (event) => {
  event.preventDefault()
  const token = tokenInput.value.trim()
  if (token.length < 16) {
    statusElement.dataset.state = 'error'
    statusElement.textContent = '令牌至少需要 16 个字符。'
    tokenInput.focus()
    return
  }

  void chrome.storage.local
    .set({ ws_url: DEFAULT_WS_URL, pairing_token: token })
    .then(() => {
      tokenInput.value = ''
      statusElement.dataset.state = 'connecting'
      statusElement.textContent = '已保存 · 正在连接本机 JobOS。'
    })
})

chrome.storage.onChanged.addListener((_changes, areaName) => {
  if (areaName === 'local') void refreshStatus()
})

void refreshStatus()
