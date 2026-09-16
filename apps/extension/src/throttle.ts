/**
 * Capture pacing + serial execution (protocol #21 §6, ADR-009).
 *
 * Red lines encoded here:
 * - the interval never drops below MIN_DELAY_MS (1800ms): jitter is applied
 *   upward only (base .. base*1.2);
 * - capture commands run strictly one at a time (SerialQueue).
 */

export const MIN_DELAY_MS = 1800
export const JITTER_RATIO = 0.2

/** Jittered interval: base × [1, 1.2], never below the 1800ms hard floor. */
export function jitteredDelay(baseMs: number = MIN_DELAY_MS, random: () => number = Math.random): number {
  const spread = Math.max(baseMs, MIN_DELAY_MS)
  const factor = 1 + random() * JITTER_RATIO
  return Math.max(MIN_DELAY_MS, Math.round(spread * factor))
}

/** Abortable sleep: resolves early when the abort flag flips. */
export function sleep(ms: number, shouldAbort?: () => boolean): Promise<void> {
  return new Promise((resolve) => {
    const started = Date.now()
    const timer = setInterval(() => {
      if ((shouldAbort && shouldAbort()) || Date.now() - started >= ms) {
        clearInterval(timer)
        resolve()
      }
    }, 100)
  })
}

/** Serial executor: tasks never overlap, regardless of caller concurrency. */
export class SerialQueue {
  private tail: Promise<unknown> = Promise.resolve()
  private inFlight = 0

  get busy(): boolean {
    return this.inFlight > 0
  }

  run<T>(task: () => Promise<T>): Promise<T> {
    const next = this.tail.then(async () => {
      this.inFlight += 1
      try {
        return await task()
      } finally {
        this.inFlight -= 1
      }
    })
    this.tail = next.catch(() => undefined)
    return next
  }
}