import { describe, expect, it } from 'vitest'

import { jitteredDelay, MIN_DELAY_MS, SerialQueue, sleep } from '../src/throttle'

describe('capture throttle', () => {
  it('never schedules below the 1800ms hard floor', () => {
    for (const value of [0, 0.25, 0.5, 0.75, 1]) {
      const delay = jitteredDelay(MIN_DELAY_MS, () => value)
      expect(delay).toBeGreaterThanOrEqual(MIN_DELAY_MS)
      expect(delay).toBeLessThanOrEqual(MIN_DELAY_MS * 1.2)
    }
  })

  it('keeps a caller-requested higher delay inside the same upward jitter band', () => {
    const base = 4000
    expect(jitteredDelay(base, () => 0)).toBe(base)
    expect(jitteredDelay(base, () => 1)).toBe(Math.round(base * 1.2))
  })

  it('raises a caller-supplied delay below the floor up to 1800ms', () => {
    expect(jitteredDelay(500, () => 0)).toBe(MIN_DELAY_MS)
  })

  it('resolves abortable sleeps', async () => {
    const started = Date.now()
    await sleep(400, () => true)
    expect(Date.now() - started).toBeLessThan(400)
  })
})

describe('serial queue', () => {
  it('never lets two capture tasks overlap', async () => {
    const queue = new SerialQueue()
    let inFlight = 0
    let peak = 0
    const task = async (): Promise<void> => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      await sleep(20)
      inFlight -= 1
    }

    await Promise.all([queue.run(task), queue.run(task), queue.run(task)])

    expect(peak).toBe(1)
    expect(queue.busy).toBe(false)
  })

  it('keeps running later tasks after a failure', async () => {
    const queue = new SerialQueue()
    const order: string[] = []

    await expect(
      queue.run(async () => {
        order.push('first')
        throw new Error('boom')
      }),
    ).rejects.toThrow('boom')
    await queue.run(async () => {
      order.push('second')
    })

    expect(order).toEqual(['first', 'second'])
  })
})