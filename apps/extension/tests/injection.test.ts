import { describe, expect, it } from 'vitest'

import { companyExtractor } from '../src/capture/company'
import { detailExtractor } from '../src/capture/detail'
import { diagnosePage } from '../src/capture/page'

/**
 * Chrome serializes an injected function and evaluates it inside the page,
 * where module scope no longer exists. Any module-scope reference therefore
 * only blows up at runtime in the browser ("x is not defined") — which is
 * exactly what silently broke the detail extractor once.
 *
 * These tests reproduce that evaluation locally: `new Function` body cannot see
 * module bindings either.
 */
type Element_ = {
  textContent: string
  innerText: string
  className: string
  nextElementSibling: null
  parentElement: null
  closest: () => null
  getBoundingClientRect: () => { width: number; height: number }
}

function evaluateInPage<T>(fn: () => T): T {
  const element: Element_ = {
    textContent: '岗位职责：负责前端交付',
    innerText: '岗位职责：负责前端交付',
    className: 'job-sec-text',
    nextElementSibling: null,
    parentElement: null,
    closest: () => null,
    getBoundingClientRect: () => ({ width: 100, height: 20 }),
  }
  const jobInfoScript = {
    textContent: [
      'var _jobInfo = {',
      "  job_id: 'synthetic-ext-id',",
      "  job_name: '合成岗位名称',",
      "  job_salary: '20-30K·14薪',",
      "  company: '合成科技有限公司',",
      '};',
    ].join('\n'),
  }
  const document = {
    title: '合成测试页-BOSS直聘',
    body: { innerText: '职位描述 负责前端开发与交付 任职要求 三年以上经验 '.repeat(20) },
    // Only the JD container matches; title/salary/company come from _jobInfo.
    querySelector: (selector: string) =>
      selector.includes('job-sec-text') ? element : null,
    querySelectorAll: (selector: string) => (selector === 'script' ? [jobInfoScript] : []),
  }
  const location = { href: 'https://www.zhipin.com/job_detail/synthetic.html' }
  const runner = new Function(
    'document',
    'location',
    `"use strict"; return (${fn.toString()})()`,
  ) as (doc: unknown, loc: unknown) => T
  return runner(document, location)
}

describe('injected functions stay self-contained', () => {
  it('detail extractor runs with no module scope available', () => {
    const result = evaluateInPage(detailExtractor)

    expect(result).toBeTruthy()
    expect((result as { url: string }).url).toContain('zhipin.com')
    expect((result as { jdText: string | null }).jdText).toBeTruthy()
  })

  it('detail extractor reads the server-rendered _jobInfo block', () => {
    const result = evaluateInPage(detailExtractor) as {
      pageData: Record<string, string>
      jobTitle: string | null
      salaryText: string | null
      company: string | null
    }

    expect(result.pageData.job_id).toBe('synthetic-ext-id')
    expect(result.jobTitle).toBe('合成岗位名称')
    expect(result.salaryText).toBe('20-30K·14薪')
    expect(result.company).toBe('合成科技有限公司')
  })

  it('company extractor runs with no module scope available', () => {
    const result = evaluateInPage(companyExtractor)

    expect(result).toBeTruthy()
    expect((result as { url: string }).url).toContain('zhipin.com')
    expect(typeof (result as { sections: Record<string, string> }).sections).toBe('object')
  })

  it('page diagnosis helper runs with no module scope available', () => {
    const result = evaluateInPage(diagnosePage)

    expect(typeof result).toBe('string')
    expect(result).toContain('title=')
  })
})