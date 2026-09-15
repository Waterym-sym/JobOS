import { describe, expect, it } from 'vitest'

import { resolveTheme, themes } from './theme'

describe('theme contract', () => {
  it('keeps the approved themes and deterministic desk fallback', () => {
    expect(themes).toEqual(['desk', 'ops', 'minimal'])
    expect(resolveTheme('ops')).toBe('ops')
    expect(resolveTheme('unknown')).toBe('desk')
    expect(resolveTheme(null)).toBe('desk')
  })
})
