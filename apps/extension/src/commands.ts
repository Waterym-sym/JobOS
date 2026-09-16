/**
 * Command execution core (protocol #21 §3).
 *
 * Implements exactly the pool-enrich commands this extension announces in
 * auth_ping: capture_details (URL form) and capture_company. Commands the
 * external bridge owns (capture_list, chat, fill, greeting) are rejected
 * explicitly instead of being silently ignored.
 *
 * Red lines encoded here: serial execution (SerialQueue), 1800ms hard delay
 * floor with upward jitter, risk pages halt the batch, no clicks/submits.
 */

import {
  buildCompanyUpdatedPayload,
  companyExtractor,
  companyIdFromUrl,
  isEmptyCompany,
} from './capture/company'
import {
  buildDetailUrl,
  buildJobUpdatedPayload,
  detailExtractor,
  isEmptyDetail,
  type DetailTarget,
} from './capture/detail'
import { diagnosePage, isRiskSignal, PageError, readPage, RiskError } from './capture/page'
import { jitteredDelay, MIN_DELAY_MS, SerialQueue, sleep } from './throttle'
import { sendEvent, sendReceipt, type CommandContext, type CommandEnvelope } from './ws-client'

const queue = new SerialQueue()
let abortRequested = false

export function isAbortRequested(): boolean {
  return abortRequested
}

function clampNumber(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.max(min, Math.min(max, Math.trunc(parsed)))
}

function detailTargets(payload: Record<string, unknown>, limit: number): DetailTarget[] {
  const targets: DetailTarget[] = []
  const entries = Array.isArray(payload.urls) ? payload.urls : []
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object') continue
    const item = entry as Record<string, unknown>
    const extId = typeof item.ext_id === 'string' ? item.ext_id : ''
    const url = typeof item.url === 'string' ? item.url : ''
    if (!extId || !url) continue
    targets.push({
      extId,
      url,
      securityId: typeof item.security_id === 'string' ? item.security_id : undefined,
    })
  }
  if (!targets.length) {
    // Legacy form: bare ext_ids; the detail URL is rebuilt from the job id.
    const ids = Array.isArray(payload.ext_ids) ? payload.ext_ids : []
    for (const id of ids) {
      if (typeof id === 'string' && id) targets.push({ extId: id, url: buildDetailUrl(id) })
    }
  }
  return targets.slice(0, Math.max(1, limit))
}

function emitPhase(
  phase: 'detail' | 'company',
  progress: { done: number; total: number; current: string },
  ctx: CommandContext,
): void {
  sendEvent('capture.phase', { phase, ...progress }, ctx)
}

function emitCompleted(ctx: CommandContext, success: number): void {
  sendEvent(
    'capture.completed',
    {
      capture_id: ctx.captureId,
      stats: { success, dup: 0, risk_halted: false },
      finished_at: new Date().toISOString(),
    },
    ctx,
  )
}

function stackHead(error: Error): string {
  const frames = (error.stack ?? '')
    .split('\n')
    .slice(1, 4)
    .map((line) => line.trim())
    .filter(Boolean)
  return frames.length ? ` @ ${frames.join(' | ')}` : ''
}

function failBatch(error: unknown, ctx: CommandContext): void {
  const message = error instanceof Error ? error.message : String(error)
  const risk = error instanceof RiskError || isRiskSignal(message)
  const code = error instanceof PageError ? error.code : risk ? 'RISK_HALTED' : 'CAPTURE_FAILED'
  // Unexpected JS errors keep their stack head: that is what makes a minified
  // service-worker failure debuggable from the server logs.
  const trace = error instanceof Error && !(error instanceof PageError) ? stackHead(error) : ''
  const detail = `${message}${trace}`.slice(0, 700)
  // Risk halts are never auto-retried server-side (ADR-009).
  sendEvent('capture.error', { code, message: detail, recoverable: !risk, risk }, ctx)
  sendReceipt('command.error', { code, message: detail }, ctx)
}

async function runDetails(payload: Record<string, unknown>, ctx: CommandContext): Promise<void> {
  const delayMs = clampNumber(payload.delay_ms, MIN_DELAY_MS, 60_000, MIN_DELAY_MS)
  const targets = detailTargets(payload, clampNumber(payload.detail_limit, 1, 100, 30))
  if (!targets.length) {
    throw new PageError('NO_TARGETS', '缺少 urls/ext_ids，无法定位详情页')
  }
  emitPhase('detail', { done: 0, total: targets.length, current: '准备详情采集…' }, ctx)

  let success = 0
  for (const [index, target] of targets.entries()) {
    if (abortRequested) break
    emitPhase(
      'detail',
      { done: index, total: targets.length, current: `打开详情页：${target.extId}` },
      ctx,
    )
    const extraction = await readPage(target.url, detailExtractor, () => abortRequested, {
      isUsable: (value) => Boolean(value) && !isEmptyDetail(value),
      diagnose: diagnosePage,
      emptyHint: `详情页未取到 JD：${target.extId}`,
      onPoll: (attempt, attempts) =>
        emitPhase(
          'detail',
          {
            done: index,
            total: targets.length,
            current: `读取详情页 ${attempt}/${attempts}：${target.extId}`,
          },
          ctx,
        ),
    })
    if (!extraction || isEmptyDetail(extraction)) {
      throw new PageError('EXTRACT_EMPTY', `详情页未取到有效内容：${target.extId}`)
    }
    sendEvent('job.updated', buildJobUpdatedPayload(target, extraction, new Date().toISOString()), ctx)
    success += 1
    emitPhase(
      'detail',
      {
        done: index + 1,
        total: targets.length,
        current: extraction.jobTitle ?? target.extId,
      },
      ctx,
    )
    if (index < targets.length - 1 && !abortRequested) {
      await sleep(jitteredDelay(delayMs), () => abortRequested)
    }
  }
  emitCompleted(ctx, success)
}

async function runCompany(payload: Record<string, unknown>, ctx: CommandContext): Promise<void> {
  const companyUrl = typeof payload.company_url === 'string' ? payload.company_url : ''
  const extCompanyId = typeof payload.ext_company_id === 'string' ? payload.ext_company_id : ''
  if (!companyUrl || !extCompanyId) {
    throw new PageError('PAYLOAD_INVALID', '缺少 company_url/ext_company_id')
  }
  emitPhase('company', { done: 0, total: 1, current: `打开公司页：${extCompanyId}` }, ctx)

  const extraction = await readPage(companyUrl, companyExtractor, () => abortRequested, {
    isUsable: (value) => Boolean(value) && !isEmptyCompany(value),
    diagnose: diagnosePage,
    emptyHint: `公司页未取到有效内容：${extCompanyId}`,
    onPoll: (attempt, attempts) =>
      emitPhase('company', { done: 0, total: 1, current: `读取公司页 ${attempt}/${attempts}` }, ctx),
  })
  const pageCompanyId = companyIdFromUrl(extraction.url)
  if (pageCompanyId && pageCompanyId !== extCompanyId) {
    throw new PageError(
      'COMPANY_ID_MISMATCH',
      `公司页与目标不一致：${pageCompanyId} ≠ ${extCompanyId}`,
    )
  }
  if (isEmptyCompany(extraction)) {
    throw new PageError('EXTRACT_EMPTY', `公司页未取到有效内容：${extCompanyId}`)
  }
  sendEvent(
    'company.updated',
    buildCompanyUpdatedPayload(extCompanyId, extraction, new Date().toISOString()),
    ctx,
  )
  emitCompleted(ctx, 1)
}

async function runCommand(command: CommandEnvelope, ctx: CommandContext): Promise<void> {
  if (!ctx.captureId) {
    sendReceipt('command.error', { code: 'NO_CAPTURE', message: 'missing capture_id' }, ctx)
    return
  }
  abortRequested = false
  sendReceipt('command.started', { type: command.type }, ctx)
  try {
    if (command.type === 'capture_details') {
      await runDetails(command.payload ?? {}, ctx)
    } else if (command.type === 'capture_company') {
      await runCompany(command.payload ?? {}, ctx)
    } else {
      throw new PageError('UNSUPPORTED_COMMAND', `本扩展不执行该命令：${command.type}`)
    }
    sendReceipt('command.completed', { type: command.type }, ctx)
  } catch (error) {
    failBatch(error, ctx)
  }
}

export function handleCommand(command: CommandEnvelope): void {
  const ctx: CommandContext = {
    captureId: command.capture_id ?? null,
    commandId: command.command_id ?? null,
  }
  // abort must not wait in the queue: it flags the in-flight batch.
  if (command.type === 'abort') {
    abortRequested = true
    sendReceipt('command.started', { type: 'abort' }, ctx)
    sendReceipt('command.completed', { type: 'abort' }, ctx)
    return
  }
  void queue.run(() => runCommand(command, ctx))
}