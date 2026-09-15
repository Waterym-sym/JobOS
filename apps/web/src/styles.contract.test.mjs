import { readFile } from 'node:fs/promises'

import { describe, expect, it } from 'vitest'

const colorLiteral = /#[0-9a-f]{3,8}\b|rgba?\(/i

describe('DESIGN.md color contract', () => {
  it('keeps color literals inside theme token declarations only', async () => {
    const [css, app] = await Promise.all([
      readFile(new URL('./styles.css', import.meta.url), 'utf8'),
      readFile(new URL('./App.tsx', import.meta.url), 'utf8'),
    ])
    const invalidCssLines = css
      .split(/\r?\n/)
      .filter((line) => colorLiteral.test(line) && !/--[\w-]+\s*:/.test(line))
    expect(invalidCssLines).toEqual([])
    expect(colorLiteral.test(app)).toBe(false)
  })
})
