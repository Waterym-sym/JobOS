/**
 * Job detail page extraction (job.updated, tier=detail).
 *
 * The extractor runs inside the page (ISOLATED world) and only reads rendered
 * DOM text — no network hooks, no clicks. Fields that are not found stay null
 * instead of being guessed (Truth Guard).
 *
 * Layered strategy (BOSS renders client-side and changes class names):
 *   1. known JD selectors;
 *   2. heading cut (职位描述/岗位职责/任职要求/公司介绍 …) — the approach proven
 *      on /gongsi/ pages;
 *   3. largest main-content container;
 *   4. whole-page visible text as the last resort.
 * `strategy` records which layer produced the JD so failures stay diagnosable.
 */

export type DetailTarget = {
  extId: string
  url: string
  securityId?: string
}

export type DetailExtraction = {
  url: string
  strategy: string
  pageData: Record<string, string>
  title: string | null
  jobTitle: string | null
  company: string | null
  salaryText: string | null
  address: string | null
  expText: string | null
  degree: string | null
  jdText: string | null
  skillTags: string[]
  bossName: string | null
  bossTitle: string | null
  activeTime: string | null
  companyDesc: string | null
  sections: Record<string, string>
}

export function buildDetailUrl(extId: string, securityId?: string): string {
  const base = `https://www.zhipin.com/job_detail/${encodeURIComponent(extId)}.html`
  return securityId ? `${base}?securityId=${encodeURIComponent(securityId)}` : base
}

/** Injected: layered DOM read with nulls when nothing matches.
 *
 * MUST stay self-contained: it is serialized and evaluated inside the page, so
 * every constant it uses is declared here (a module-scope reference would only
 * throw "x is not defined" at injection time). See tests/injection.test.ts.
 */
export function detailExtractor(): DetailExtraction {
  const MAX_TEXT = 6000
  const clean = (value: string | null | undefined): string =>
    (value ?? '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim()
  const blockText = (value: string | null | undefined): string =>
    (value ?? '')
      .replace(/\u00a0/g, ' ')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .join('\n')
      .trim()
  const pick = (selectors: string[]): string | null => {
    for (const selector of selectors) {
      const text = clean(document.querySelector(selector)?.textContent)
      if (text) return text
    }
    return null
  }
  const pickAll = (selectors: string[]): string[] => {
    for (const selector of selectors) {
      const values = Array.from(document.querySelectorAll(selector))
        .map((node) => clean(node.textContent))
        .filter((value): value is string => Boolean(value))
      if (values.length) return values
    }
    return []
  }

  const JD_HEADINGS = [
    '职位描述',
    '岗位职责',
    '工作内容',
    '工作职责',
    '主要职责',
    '职位要求',
    '任职要求',
    '任职资格',
    '任职条件',
    '岗位要求',
    '岗位介绍',
    '职位详情',
    '我们希望你',
    '你将负责',
    '加分项',
  ]
  const COMPANY_HEADINGS = ['公司介绍', '公司简介', '企业介绍', '工商信息', '公司信息', '团队介绍']

  // ---- L0: server-rendered page data (inline `var _jobInfo = {...}` block).
  // Passive DOM read of a script tag's text; no page JS is touched.
  const pageData: Record<string, string> = {}
  for (const script of Array.from(document.querySelectorAll('script'))) {
    const text = script.textContent ?? ''
    if (!text.includes('_jobInfo')) continue
    for (const key of ['job_id', 'job_name', 'job_salary', 'company']) {
      const match = new RegExp(`${key}\\s*:\\s*'([^']*)'`).exec(text)
      const value = match?.[1]
      if (value) pageData[key] = value.replace(/\s+/g, ' ').trim()
    }
  }

  // ---- L1: known JD containers
  const directJd = pick([
    '.job-sec-text',
    '[class*="job-sec-text"]',
    '.job-detail-section',
    '[class*="job-detail-section"]',
    '.detail-content .text',
    '[class*="detail-content"] .text',
  ])

  // ---- L2: heading cut
  const sections: Record<string, string> = {}
  const headingHits: string[] = []
  const seen = new Set<string>()
  const headingNodes = Array.from(
    document.querySelectorAll('h1,h2,h3,h4,h5,dt,strong,b,[class*="title"],[class*="sub-title"]'),
  )
  for (const node of headingNodes) {
    const text = clean(node.textContent)
    if (!text || text.length > 14) continue
    const names = [...JD_HEADINGS, ...COMPANY_HEADINGS]
    const matched = names.find((name) => text === name || text.includes(name))
    if (!matched || seen.has(matched)) continue
    if (/^(nav|footer|header)$/i.test(node.closest('nav,footer,header')?.tagName ?? '')) continue
    seen.add(matched)

    const chunks: string[] = []
    let sibling = node.nextElementSibling
    while (sibling && chunks.join('\n').length < MAX_TEXT) {
      const text2 = blockText((sibling as HTMLElement).innerText ?? sibling.textContent)
      if (text2) chunks.push(text2)
      sibling = sibling.nextElementSibling
    }
    let content = chunks.join('\n').trim()
    if (content.length < 20) {
      const box = node.parentElement?.parentElement ?? node.parentElement
      content = blockText(box?.innerText ?? box?.textContent).replace(text, '').trim()
    }
    if (content.length >= 20) {
      sections[matched] = content.slice(0, MAX_TEXT)
      headingHits.push(matched)
    }
  }

  // ---- L3: largest main container
  const containerCandidates = [
    ...Array.from(document.querySelectorAll<HTMLElement>('main, #main, article')),
    ...Array.from(
      document.querySelectorAll<HTMLElement>(
        '[class*="job-detail"], [class*="detail-container"], [class*="job-detail-container"]',
      ),
    ),
  ]
  let containerText = ''
  for (const node of containerCandidates) {
    const text = blockText(node.innerText)
    if (text.length > containerText.length) containerText = text
  }

  // ---- L4: whole page
  const bodyText = blockText(document.body?.innerText).slice(0, MAX_TEXT)

  const jdFromHeadings = JD_HEADINGS.map((name) => sections[name])
    .filter((value): value is string => Boolean(value))
    .join('\n')
    .trim()
  const companyFromHeadings = COMPANY_HEADINGS.map((name) => sections[name])
    .filter((value): value is string => Boolean(value))
    .join('\n')
    .trim()

  let strategy = 'none'
  let jdText: string | null = null
  if (directJd) {
    strategy = 'selector'
    jdText = directJd.slice(0, MAX_TEXT)
  } else if (jdFromHeadings) {
    strategy = 'headings'
    jdText = jdFromHeadings.slice(0, MAX_TEXT)
  } else if (containerText.length >= 120) {
    strategy = 'container'
    jdText = containerText.slice(0, MAX_TEXT)
  } else if (bodyText.length >= 120) {
    strategy = 'body'
    jdText = bodyText
  }

  const companyDesc = companyFromHeadings || null
  if (jdText) sections.jd = jdText
  if (companyDesc) sections.company = companyDesc.slice(0, 2000)

  // DOM values win when present; the server-rendered block fills the gaps.
  const domTitle = pick(['.job-primary .name h1', '.job-name', '.name h1', '[class*="job-name"]', 'h1'])
  const domCompany = pick([
    '.job-primary .company-info .name',
    '.company-info a.name',
    '[class*="company-name"]',
  ])
  const domSalary = pick(['.job-primary .salary', '[class*="salary"]'])

  return {
    url: location.href,
    strategy,
    pageData,
    title: clean(document.title) || null,
    jobTitle: domTitle ?? pageData.job_name ?? null,
    company: domCompany ?? pageData.company ?? null,
    salaryText: domSalary ?? pageData.job_salary ?? null,
    address: pick(['.location-address', '[class*="location-address"]', '[class*="job-address"] .text']),
    expText: pick(['.job-primary .job-info .text', '[class*="job-limit"] .text']),
    degree: null,
    jdText,
    skillTags: pickAll(['.job-keyword-list li', '[class*="job-keyword-list"] li', '.tag-all .tag-item']),
    bossName: pick(['.job-boss-info .name', '.boss-info .name', '[class*="boss-info"] .name', '[class*="boss-name"]']),
    bossTitle: pick(['.boss-info .boss-title', '[class*="boss-info"] [class*="title"]']),
    activeTime: pick(['.boss-active-time', '[class*="boss-active-time"]']),
    companyDesc,
    sections,
  }
}

/** Extension-side payload builder: contract keys only, absent values omitted. */
export function buildJobUpdatedPayload(
  target: DetailTarget,
  extraction: DetailExtraction,
  capturedAt: string,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    source: 'boss',
    ext_id: target.extId,
    tier: 'detail',
    detail_json: {
      url: extraction.url,
      strategy: extraction.strategy,
      pageData: extraction.pageData,
      title: extraction.title,
      sections: extraction.sections,
      skillTags: extraction.skillTags,
      capturedAt,
    },
    captured_at: capturedAt,
  }
  const assign = (key: string, value: string | null): void => {
    if (value) payload[key] = value
  }
  assign('title', extraction.jobTitle)
  assign('company', extraction.company)
  assign('salary_text', extraction.salaryText)
  assign('address', extraction.address)
  assign('exp_text', extraction.expText)
  assign('degree', extraction.degree)
  assign('jd_text', extraction.jdText)
  assign('boss_name', extraction.bossName)
  assign('company_desc', extraction.companyDesc)
  assign('active_time', extraction.activeTime)
  if (extraction.skillTags.length) payload.skill_tags = extraction.skillTags
  if (extraction.bossName || extraction.bossTitle) {
    payload.boss_json = {
      ...(extraction.bossName ? { name: extraction.bossName } : {}),
      ...(extraction.bossTitle ? { title: extraction.bossTitle } : {}),
    }
  }
  return payload
}

/** A detail capture that found no JD at all is a failure, not data. */
export function isEmptyDetail(extraction: DetailExtraction): boolean {
  return !extraction.jdText
}