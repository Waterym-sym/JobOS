/** JD 原文分节与关键词抽取（纯函数，零 LLM）。
 *
 * 小节标题与条数都来自职位详情原文本身：不同岗位的小节集合不同，所以这里
 * 只做「识别」，不做固定模板；识别不出来时整段归入「职位简介」，不丢内容。
 */

export type JdSection = {
  title: string
  items: string[]
}

/** 常见小节名提示（仅作为识别加成，不是唯一入口）。 */
const SECTION_HINTS = [
  '岗位职责', '工作职责', '职位职责', '职责描述', '工作内容', '岗位描述', '职位描述',
  '任职要求', '任职资格', '岗位要求', '任职条件', '我们希望你', '希望你',
  '加分项', '优先项', '合作方式', '适合这样的人', '适合人群',
  '职位简介', '职位亮点', '岗位亮点', '你将获得', '我们提供', '福利待遇', '团队介绍',
]

const MAX_TITLE_CHARS = 18
const MAX_SHORT_TITLE_CHARS = 12
const PARAGRAPH_MIN_CHARS = 30
const MAX_KEYWORDS = 18

function normalizeTitle(line: string): string {
  return line
    .replace(/^[\s（(【[]*/, '')
    .replace(/^[一二三四五六七八九十\d]+[、.．)）]\s*/, '')
    .replace(/[：:]\s*$/, '')
    .trim()
}

function isHeading(line: string, next: string | undefined): boolean {
  if (line.length < 2 || line.length > MAX_TITLE_CHARS) return false
  if (/[。！？；!?;]$/.test(line)) return false
  const title = normalizeTitle(line)
  if (!title) return false
  if (/[：:]$/.test(line)) return true
  if (SECTION_HINTS.some((hint) => title === hint || title.startsWith(hint))) return true
  // 短行 + 下一行是长段落 + 行内无句读 + 不是项目符号 → 视为小节标题
  if (/^[·•\-*\d]/.test(line)) return false
  return (
    title.length <= MAX_SHORT_TITLE_CHARS &&
    !/[，,、]/.test(title) &&
    (next?.length ?? 0) >= PARAGRAPH_MIN_CHARS
  )
}

// BOSS 详情常见把整份 JD 压成一行（「岗位职责1、…2、…。任职要求1、…」）。
// 这里只按原文里本来就有的标题词与数字编号做结构性断行/去序号，正文一个字不增改。
const TITLE_SPLIT_RE = new RegExp(`(?:${SECTION_HINTS.join('|')})`, 'g')
const HEADING_BEFORE_OK = /[。！？；;\n]/
// 1、 / 1. / 1）：排除小数（3.5）、范围（1-3、）与版本号（v6.1）。
const NUMBERED_ITEM_RE = /(?<![\d.])(?<!\d[-—–~至])\d{1,2}\s*[、.．)]\s*(?!\d)/g
const PAREN_NUMBERED_RE = /[（(]\s*\d{1,2}\s*[）)]\s*/g

function structureJdText(raw: string): string {
  // 1) 行内小节标题：标题位于串首或句末标点之后时，在其前后断行。
  let text = raw
  let out = ''
  let last = 0
  let match: RegExpExecArray | null
  TITLE_SPLIT_RE.lastIndex = 0
  while ((match = TITLE_SPLIT_RE.exec(text))) {
    const before = match.index === 0 ? '' : text[match.index - 1] ?? ''
    if (before && !HEADING_BEFORE_OK.test(before)) continue
    out += text.slice(last, match.index)
    if (match.index > 0) out += '\n'
    out += match[0]
    last = match.index + match[0].length
    const after = text[last] ?? ''
    if (after && !/[\n：:]/.test(after)) out += '\n'
  }
  out += text.slice(last)

  // 2) 数字编号条目前断行；编号保留在原文里（展示层用 displayItem 剥离，
  //    同时让「数字开头不是小节标题」的启发式继续生效）。
  return out.replace(NUMBERED_ITEM_RE, '\n$&').replace(PAREN_NUMBERED_RE, '\n$&')
}

const ITEM_NUMBER_PREFIX = /^(?:[（(]\s*\d{1,2}\s*[）)]|\d{1,2}\s*[、.．)])\s*/

/** 展示用：去掉条目原文自带的数字编号（序号由列表样式承载）；无编号原样返回。 */
export function displayItem(item: string): string {
  return item.replace(ITEM_NUMBER_PREFIX, '')
}

/** 从 JD 原文切出小节；无小节时整段归入「职位简介」。 */
export function parseJdSections(jdText: string | null): JdSection[] {
  const lines = structureJdText(jdText ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  if (lines.length === 0) return []

  const sections: JdSection[] = []
  let current: JdSection | null = null
  lines.forEach((line, index) => {
    if (isHeading(line, lines[index + 1])) {
      current = { title: normalizeTitle(line), items: [] }
      sections.push(current)
      return
    }
    if (current === null) {
      current = { title: '职位简介', items: [] }
      sections.push(current)
    }
    current.items.push(line)
  })
  return sections.filter((section) => section.items.length > 0)
}

/** 分节呈现形态：全是短词 → 标签；只有一条长文本 → 段落；其余 → 编号列表。 */
export function sectionShape(items: readonly string[]): 'chips' | 'paragraph' | 'list' {
  if (items.length > 0 && items.every((item) => item.length <= 14)) return 'chips'
  if (items.length === 1) return 'paragraph'
  return 'list'
}

/** 只保留 JD 原文里确实出现过（或来自技能标签）的关键词，不猜测。 */
const KEYWORD_HINTS = [
  'Dify', 'Coze', 'FastGPT', 'n8n', 'RAG', 'LLM', 'AIGC', 'Agent', 'Prompt',
  'Python', 'Node.js', 'TypeScript', 'JavaScript', 'React', 'Vue', 'Java', 'Go',
  'SQL', 'PostgreSQL', 'MySQL', 'Redis', 'Docker', 'Kubernetes', 'API',
  '飞书', '企微', '钉钉', 'Notion', '低代码', 'SaaS', 'ERP', 'CRM',
  '大模型', '智能体', '工作流', '知识库', '提示词', '向量数据库', '微调',
  '前端', '后端', '全栈', '数据分析', '项目交付', 'Demo',
]

function containsHint(text: string, hint: string): boolean {
  if (/^[\x20-\x7E]+$/.test(hint)) {
    const escaped = hint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, 'i').test(text)
  }
  return text.includes(hint)
}

export function jdKeywords(jdText: string | null, skillTags: readonly string[]): string[] {
  const text = jdText ?? ''
  const found: string[] = []
  const seen = new Set<string>()
  const push = (value: string) => {
    const trimmed = value.trim()
    if (!trimmed || found.length >= MAX_KEYWORDS) return
    const key = trimmed.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    found.push(trimmed)
  }

  for (const tag of skillTags) push(tag)
  for (const hint of KEYWORD_HINTS) {
    if (containsHint(text, hint)) push(hint)
  }
  return found
}