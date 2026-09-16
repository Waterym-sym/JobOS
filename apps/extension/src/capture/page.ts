/**
 * Background-tab page reader: opens one BOSS page, passively extracts data,
 * and always closes the tab again.
 *
 * Red lines encoded here:
 * - only https://www.zhipin.com/* URLs may be opened;
 * - tabs are opened inactive and we never click, type or submit anything;
 * - risk/verification pages raise RiskError so the batch halts (ADR-009).
 *
 * BOSS pages render client-side, so extraction polls the DOM until the caller's
 * `isUsable` predicate passes (or the attempt budget runs out) instead of
 * trusting a single fixed delay.
 */

const ALLOWED_PREFIX = 'https://www.zhipin.com/'
const RISK_RE = /账户存在异常|账号存在异常|风控|安全验证|环境存在异常|异常访问/i
const LOAD_TIMEOUT_MS = 25_000
const RENDER_SETTLE_MS = 600
const EXTRACT_ATTEMPTS = 10
const EXTRACT_INTERVAL_MS = 1200

export class RiskError extends Error {
  readonly risk = true

  constructor(message: string) {
    super(message)
    this.name = 'RiskError'
  }
}

export class PageError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'PageError'
    this.code = code
  }
}

type PageSignals = {
  url: string
  title: string
  text: string
}

/** Injected: page identity + visible-text head used for risk detection. */
function readSignals(): PageSignals {
  const text = document.body?.innerText ?? ''
  return { url: location.href, title: document.title, text: text.slice(0, 4000) }
}

export function isRiskSignal(text: string): boolean {
  return RISK_RE.test(text)
}

export function isAllowedPageUrl(url: string): boolean {
  return url.startsWith(ALLOWED_PREFIX)
}

async function waitForComplete(tabId: number): Promise<void> {
  const deadline = Date.now() + LOAD_TIMEOUT_MS
  while (Date.now() < deadline) {
    const tab = await chrome.tabs.get(tabId).catch(() => undefined)
    if (tab?.status === 'complete') return
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new PageError('PAGE_TIMEOUT', '页面加载超时')
}

type InjectionResult<T> = {
  result?: T
  exceptionDetails?: { text?: string; exception?: { description?: string; value?: unknown } }
}

async function inject<T>(tabId: number, func: () => T): Promise<T> {
  const [result] = (await chrome.scripting.executeScript({
    target: { tabId },
    func,
  })) as InjectionResult<T>[]
  if (!result) throw new PageError('EXTRACT_FAILED', '页面注入未返回结果')
  if (result.exceptionDetails) {
    // Surface the page-side error instead of swallowing it: this is how we
    // learn what the injected extractor actually hit.
    const details = result.exceptionDetails
    const text =
      details.exception?.description ?? details.exception?.value ?? details.text ?? 'unknown'
    throw new PageError('PAGE_SCRIPT_ERROR', `页面注入执行出错：${String(text).slice(0, 300)}`)
  }
  return result.result as T
}

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export type ReadPageOptions<T> = {
  /** Polling stops as soon as this returns true (content rendered). */
  isUsable?: (value: T) => boolean
  /** Injected diagnostic run when the budget is spent without usable content. */
  diagnose?: () => string
  emptyHint?: string
  attempts?: number
  intervalMs?: number
  /** Heartbeat per polling round, so a stuck run is distinguishable from silence. */
  onPoll?: (attempt: number, attempts: number) => void
}

/** Open `url` in an inactive tab, poll-read it, close it. Never leaves tabs behind. */
export async function readPage<T>(
  url: string,
  extractor: () => T,
  shouldAbort?: () => boolean,
  options: ReadPageOptions<T> = {},
): Promise<T> {
  if (!isAllowedPageUrl(url)) {
    throw new PageError('HOST_NOT_ALLOWED', '仅允许打开 BOSS 站内页面')
  }
  const attempts = options.attempts ?? EXTRACT_ATTEMPTS
  const intervalMs = options.intervalMs ?? EXTRACT_INTERVAL_MS
  const tab = await chrome.tabs.create({ url, active: false })
  const tabId = tab.id
  try {
    if (tabId == null) throw new PageError('TAB_CREATE_FAILED', '无法创建采集标签页')
    await waitForComplete(tabId)
    await pause(RENDER_SETTLE_MS)

    let last: T | undefined
    let emptied = false
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (shouldAbort?.()) throw new PageError('ABORTED', '批次已中止')
      options.onPoll?.(attempt + 1, attempts)
      const signals = await inject<PageSignals>(tabId, readSignals)
      if (isRiskSignal(`${signals.title}\n${signals.text}`)) {
        throw new RiskError(`页面出现风控/验证特征：${signals.title}`)
      }
      last = await inject<T>(tabId, extractor)
      // A missing return value is "not usable yet", never a crash.
      if (last == null) {
        emptied = true
      } else if (!options.isUsable || options.isUsable(last)) {
        return last
      }
      if (attempt < attempts - 1) await pause(intervalMs)
    }
    if (options.isUsable && (last == null || !options.isUsable(last))) {
      // Keep the diagnostic with the failure: one run is enough to see what
      // the page actually rendered instead of guessing at selectors.
      const diagnosis = options.diagnose
        ? await inject<string>(tabId, options.diagnose).catch(() => '')
        : ''
      const reason = last == null ? '页面注入未返回任何内容（empty=' + emptied + '）' : options.emptyHint ?? '页面未取到有效内容'
      const message = `${reason}${diagnosis ? ` | ${diagnosis}` : ''}`
      throw new PageError('EXTRACT_EMPTY', message.slice(0, 700))
    }
    if (last == null) throw new PageError('EXTRACT_FAILED', '页面注入未返回结果')
    return last
  } finally {
    if (tabId != null) await chrome.tabs.remove(tabId).catch(() => undefined)
  }
}

/** Injected: short structural diagnosis used when extraction comes up empty. */
export function diagnosePage(): string {
  const clean = (value: string | null | undefined): string =>
    (value ?? '').replace(/\s+/g, ' ').trim()
  const classes = new Map<string, number>()
  for (const node of Array.from(document.querySelectorAll<HTMLElement>('div,section,article')).slice(0, 400)) {
    const text = clean(node.innerText)
    if (text.length < 40) continue
    const key = clean(node.className).split(' ').filter(Boolean).slice(0, 3).join('.')
    if (!key) continue
    classes.set(key, Math.max(classes.get(key) ?? 0, text.length))
  }
  const top = Array.from(classes.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8)
    .map(([key, size]) => `${key}(${size})`)
  const body = clean(document.body?.innerText).slice(0, 240)
  return `title=${clean(document.title).slice(0, 80)} | blocks=${top.join(', ')} | text=${body}`
}