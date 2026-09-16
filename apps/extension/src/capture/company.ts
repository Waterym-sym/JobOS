/**
 * Company profile page extraction (company.updated).
 *
 * Same rules as the detail extractor: read-only DOM access, no clicks, no
 * network hooks, and the ext_company_id claimed by this page must match the
 * target the server asked for.
 *
 * Algorithm ported from the proven /gongsi/ capture flow: cut the page by
 * section headings (人才发展 / 工作时间及福利 / 产品介绍 / 工商信息 / 公司地址 /
 * 高管介绍 / 招聘Boss) and fall back to plain-text cutting when the DOM shape
 * is unknown. Missing sections stay absent — never invented.
 */

const GONGSI_RE = /\/gongsi\/([^/]+?)\.html/i

export type CompanyExtraction = {
  url: string
  pageTitle: string
  name: string | null
  sections: Record<string, string>
}

export function companyIdFromUrl(url: string): string | null {
  const match = GONGSI_RE.exec(url)
  const value = match?.[1]
  return value ? decodeURIComponent(value) : null
}

/**
 * 公司页名称节点常把「收藏 / 已收藏」按钮文字并进来（实测库里出现
 * 「杭州天星橙人工智能收藏」）。只剥离名称末尾的收藏词，名称本体一个字不动；
 * 「XX收藏有限公司」这类以「公司」结尾的全称不受影响。
 */
export function sanitizeCompanyName(value: string | null | undefined): string | null {
  const cleaned = (value ?? '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim()
  if (!cleaned) return null
  const stripped = cleaned.replace(/(?:已?收藏)+$/, '').trim()
  return stripped || null
}

/** Injected: section-cut read of a /gongsi/ page.
 *
 * MUST stay self-contained: it is serialized and evaluated inside the page, so
 * the section table and limits are declared here rather than at module scope.
 */
export function companyExtractor(): CompanyExtraction {
  const MAX_SECTION = 6000
  const SECTION_DEFS: { key: string; names: string[] }[] = [
    { key: 'talent', names: ['人才发展'] },
    { key: 'benefits', names: ['工作时间及福利', '工作时间', '员工福利'] },
    { key: 'products', names: ['产品介绍', '公司产品'] },
    { key: 'business', names: ['工商信息'] },
    { key: 'address', names: ['公司地址', '办公地址'] },
    { key: 'executives', names: ['高管介绍', '管理团队'] },
    { key: 'bosses', names: ['招聘Boss', '招聘boss', '招聘 BOSS', '招贤纳士'] },
    { key: 'intro', names: ['公司介绍', '公司简介', '企业介绍'] },
  ]
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

  const matchSectionName = (value: string): string | null => {
    const text = clean(value)
    if (!text || text.length > 12) return null
    for (const def of SECTION_DEFS) {
      if (def.names.some((name) => text === name || text.includes(name))) return def.key
    }
    return null
  }

  const contentAfterHeading = (heading: Element): string => {
    const headingText = clean(heading.textContent)
    let box: Element | null = heading.parentElement
    for (let index = 0; index < 2 && box && box !== document.body; index += 1) {
      if (blockText(box.textContent).length >= headingText.length + 12) break
      box = box.parentElement
    }
    if (!box || box === document.body) return ''

    const chunks: string[] = []
    let sibling = heading.nextElementSibling
    while (sibling && chunks.join('\n').length < MAX_SECTION) {
      const text = blockText((sibling as HTMLElement).innerText ?? sibling.textContent)
      if (text) chunks.push(text)
      sibling = sibling.nextElementSibling
    }
    const fromSiblings = chunks.join('\n').trim()
    if (fromSiblings.length >= 8) return fromSiblings.slice(0, MAX_SECTION)

    const fallback = blockText((box as HTMLElement).innerText ?? box.textContent)
    return fallback.replace(clean(heading.textContent), '').trim().slice(0, MAX_SECTION)
  }

  const cutFromPlainText = (): Record<string, string> => {
    const body = blockText(document.body?.innerText)
    if (!body) return {}
    const allNames = SECTION_DEFS.flatMap((def) => def.names)
    const sections: Record<string, string> = {}
    for (const def of SECTION_DEFS) {
      const names = def.names.join('|')
      const stop = allNames.join('|')
      const pattern = new RegExp(`(?:${names})[：:]?\\s*\\n?([^\\n]*(?:\\n(?!${stop})[^\\n]*)*)`)
      const match = body.match(pattern)
      if (match?.[1]) {
        const text = blockText(match[1])
        if (text.length >= 2) sections[def.key] = text.slice(0, MAX_SECTION)
      }
    }
    return sections
  }

  const headings: { key: string; node: Element }[] = []
  const seen = new Set<string>()
  for (const node of Array.from(
    document.querySelectorAll("h1,h2,h3,h4,h5,[class*='title'],[class*='sub-title'],dt,strong,b"),
  )) {
    const key = matchSectionName(node.textContent ?? '')
    if (!key || seen.has(key)) continue
    if (/^(nav|footer|header)$/i.test(node.closest('nav,footer,header')?.tagName ?? '')) continue
    seen.add(key)
    headings.push({ key, node })
  }

  const sections: Record<string, string> = {}
  for (const { key, node } of headings) {
    const text = contentAfterHeading(node)
    if (text) sections[key] = text
  }

  const merged = Object.keys(sections).length ? sections : cutFromPlainText()

  // Injected copy of sanitizeCompanyName: MUST stay inline (no module refs in page).
  const sanitizeName = (value: string | null | undefined): string | null => {
    const stripped = (value ?? '').trim().replace(/(?:已?收藏)+$/, '').trim()
    return stripped || null
  }

  const findName = (): string | null => {
    const selectors = ['.company-name', "[class*='company-name']", '.name', 'h1', '.info-company .name']
    for (const selector of selectors) {
      const text = clean(document.querySelector(selector)?.textContent)
      if (text && text.length <= 60) return sanitizeName(text)
    }
    const fromTitle = clean(document.title).replace(/[-_]?BOSS直聘.*$/, '').trim()
    return sanitizeName(fromTitle)
  }

  return {
    url: location.href,
    pageTitle: clean(document.title),
    name: findName(),
    sections: merged,
  }
}

export function buildCompanyUpdatedPayload(
  extCompanyId: string,
  extraction: CompanyExtraction,
  capturedAt: string,
): Record<string, unknown> {
  const safeName = sanitizeCompanyName(extraction.name)
  return {
    source: 'boss',
    ext_company_id: extCompanyId,
    ...(safeName ? { name: safeName } : {}),
    sections: extraction.sections,
    raw_json: {
      url: extraction.url,
      pageTitle: extraction.pageTitle,
      capturedAt,
    },
    captured_at: capturedAt,
  }
}

export function isEmptyCompany(extraction: CompanyExtraction): boolean {
  return !extraction.name && Object.keys(extraction.sections).length === 0
}