import { readFile } from 'node:fs/promises'

import { describe, expect, it } from 'vitest'

const colorLiteral = /#[0-9a-f]{3,8}\b|rgba?\(/i

describe('DESIGN.md color contract', () => {
  it('keeps color literals inside theme token declarations only', async () => {
    const [css, ...sources] = await Promise.all([
      readFile(new URL('./styles.css', import.meta.url), 'utf8'),
      readFile(new URL('./App.tsx', import.meta.url), 'utf8'),
      readFile(new URL('./pages_jobs.tsx', import.meta.url), 'utf8'),
      readFile(new URL('./pages_screening.tsx', import.meta.url), 'utf8'),
      readFile(new URL('./job-profile-view.tsx', import.meta.url), 'utf8'),
      readFile(new URL('./job-detail-card.tsx', import.meta.url), 'utf8'),
    ])
    const invalidCssLines = css
      .split(/\r?\n/)
      .filter((line) => colorLiteral.test(line) && !/--[\w-]+\s*:/.test(line))
    expect(invalidCssLines).toEqual([])
    for (const source of sources) {
      expect(colorLiteral.test(source)).toBe(false)
    }
  })
})
