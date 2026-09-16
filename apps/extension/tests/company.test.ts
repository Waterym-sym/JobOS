import { describe, expect, it } from 'vitest'

import {
  buildCompanyUpdatedPayload,
  companyExtractor,
  sanitizeCompanyName,
} from '../src/capture/company'

describe('sanitizeCompanyName', () => {
  it('strips the trailing 收藏 button text merged into the company name node', () => {
    expect(sanitizeCompanyName('杭州天星橙人工智能收藏')).toBe('杭州天星橙人工智能')
    expect(sanitizeCompanyName('  魔筷科技  已收藏 ')).toBe('魔筷科技')
  })

  it('never touches names that merely contain 收藏 mid-string', () => {
    expect(sanitizeCompanyName('某某收藏文化有限公司')).toBe('某某收藏文化有限公司')
  })

  it('normalizes blank/nbsp to null instead of inventing a name', () => {
    expect(sanitizeCompanyName('')).toBeNull()
    expect(sanitizeCompanyName('收藏')).toBeNull()
    expect(sanitizeCompanyName(null)).toBeNull()
  })
})

describe('companyExtractor name capture (in-page evaluation)', () => {
  /** Same serialization constraint as injection.test.ts: no module scope in page. */
  function evaluateCompanyExtractor(doc: unknown, loc: unknown) {
    const runner = new Function(
      'document',
      'location',
      `"use strict"; return (${companyExtractor.toString()})()`,
    ) as (d: unknown, l: unknown) => { name: string | null }
    return runner(doc, loc)
  }

  function docWithName(rawName: string) {
    const element = {
      textContent: rawName,
      innerText: rawName,
      parentElement: null,
      nextElementSibling: null,
      closest: () => null,
    }
    return {
      title: '杭州天星橙人工智能收藏 - BOSS直聘',
      body: { innerText: '' },
      querySelector: (selector: string) => (selector === '.company-name' ? element : null),
      querySelectorAll: () => [],
    }
  }

  it('strips 收藏 from the name node when serialized into the page', () => {
    const result = evaluateCompanyExtractor(
      docWithName('杭州天星橙人工智能收藏'),
      { href: 'https://www.zhipin.com/gongsi/synthetic~.html' },
    )
    expect(result.name).toBe('杭州天星橙人工智能')
  })
})

describe('buildCompanyUpdatedPayload', () => {
  it('sanitizes the name before sending', () => {
    const payload = buildCompanyUpdatedPayload(
      'synth~',
      {
        url: 'https://www.zhipin.com/gongsi/synth~.html',
        pageTitle: '魔筷科技收藏 - BOSS直聘',
        name: '魔筷科技收藏',
        sections: {},
      },
      '2026-09-17T00:00:00Z',
    )
    expect(payload.name).toBe('魔筷科技')
  })
})
