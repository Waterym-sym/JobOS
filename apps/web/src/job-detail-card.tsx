import type { ReactNode } from 'react'
import { displayItem, parseJdSections, sectionShape, type JdSection } from './lib/jd-sections'
import type { JobProfileCompany, JobProfileJob } from './lib/capture'

const PENDING_DOSSIER_ACTIONS: readonly { label: string; reason: string }[] = [
  { label: '查看原岗位', reason: '未接入：来源链接尚未进入接口契约' },
  { label: '生成定制简历', reason: '未接入：三形态简历与模板引擎尚未实现' },
  { label: '生成沟通话术', reason: '未接入：招呼语与 Guard 尚未实现' },
  { label: '面试准备', reason: '未接入：面试准备材料尚未实现' },
  { label: '加入投递', reason: '未接入：投递包尚未实现' },
]

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

/** 采集文本夹带的页面控件文案：仅整行相等时剔除，正文一个字不动。 */
const NOISE_LINES = new Set(['展开', '收起', '查看更多信息', '查看所有职位', '点击查看地图'])

export function sectionLines(value: unknown): string[] {
  const raw = text(value)
  if (!raw) return []
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !NOISE_LINES.has(line))
}

/** 工商信息：采集形态为「标签行（以：结尾）+ 下一行为值」；配不上对的行不展示。 */
export function parseBusinessRows(value: unknown): [string, string][] {
  const lines = sectionLines(value)
  const rows: [string, string][] = []
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (!line) continue
    const match = /^(.{1,12}?)[：:]\s*(.*)$/.exec(line)
    if (!match) continue
    const label = match[1]?.trim()
    let content = match[2]?.trim() ?? ''
    if (!content) {
      const next = lines[i + 1]
      if (next && !/[：:]\s*$/.test(next)) {
        content = next.trim()
        i += 1
      }
    }
    if (label && content) rows.push([label, content])
  }
  return rows
}

type Recruiter = { name: string; title: string | null; note: string | null; current: boolean }

// 招聘 Boss 区块把姓名与职位连写（如「陈金朋高级营销总监」），只能按已知职位词切分；识别不出不猜。
// 职位词头 = 可堆叠的领域/地域前缀 + 职位后缀；取全串最早出现的位置作为切点。
const TITLE_PREFIX =
  '高级|资深|首席|常务|执行|副|助理|区域|全国|海外|国际|中国|总部' +
  '|营销|市场|销售|商务|渠道|品牌|公关|运营|内容|产品|技术|设计|数据|算法|前端|后端|测试|运维' +
  '|人力|人事|行政|财务|投资|法务|战略|组织|综合|管理|项目|交付|解决|售前|售后|客户' +
  '|直播|电商|供应链|采购|质量|硬件|医疗|教育|游戏|增长' +
  '|北京|上海|广州|深圳|杭州|成都|南京|武汉|西安|苏州|重庆|天津|香港'
const TITLE_MARK = new RegExp(
  `联合创始人|创始人(?:兼\\w+)?|董事长|合伙人` +
    `|(?:${TITLE_PREFIX})*(?:总经理|总裁|总监|负责人|主管|经理|主任|专家|顾问|助理|专员|工程师)` +
    `|HRBP|HR|hr|招聘[\\u4e00-\\u9fa5A-Z]{0,2}|人事[\\u4e00-\\u9fa5A-Z]{0,3}` +
    `|CEO|COO|CTO|CFO|CMO`,
)
const NAME_SUFFIX = /先生|女士|老师/

export function splitNameTitle(line: string): { name: string; title: string | null } {
  // X先生 / X女士：切点在称呼之后，称呼属于姓名。
  const suffix = NAME_SUFFIX.exec(line)
  if (suffix && suffix.index >= 1 && suffix.index <= 3) {
    const cut = suffix.index + suffix[0].length
    const title = line.slice(cut).trim()
    return { name: line.slice(0, cut).trim(), title: title || null }
  }
  const match = TITLE_MARK.exec(line)
  if (match && match.index >= 1) {
    return { name: line.slice(0, match.index).trim(), title: line.slice(match.index).trim() }
  }
  return { name: line.trim(), title: null }
}

/** 招聘Boss 区块：每位招聘官两行——首行姓名（职位连写），次行「正在招聘…」。不合结构的行跳过。 */
export function parseBosses(value: unknown): Recruiter[] {
  const lines = sectionLines(value)
  const people: Recruiter[] = []
  for (let i = 0; i < lines.length; i += 1) {
    const head = lines[i]
    const next = lines[i + 1]
    if (!head || !next || !/^正在招聘/.test(next)) continue
    const { name, title } = splitNameTitle(head)
    if (name) people.push({ name, title, note: next, current: false })
    i += 1
  }
  return people
}

const CLOCK_LINE = /\d{1,2}\s*[:：]\s*\d{2}|上午|下午|早上|晚上|凌晨/
const BENEFIT_SPLIT = /[、,，/／]/

/** 工作时间：取含上/下班时刻的原文行（放在卡片标题后做摘要），无则 null。 */
export function parseWorkTime(value: unknown): string | null {
  return sectionLines(value).find((line) => CLOCK_LINE.test(line) && line.length <= 40) ?? null
}

/** 工作时间及福利：去掉上/下班时刻行，其余按短词拆成福利标签并按原文顺序去重。 */
export function parseBenefits(value: unknown): string[] {
  const tags: string[] = []
  const seen = new Set<string>()
  for (const line of sectionLines(value)) {
    if (CLOCK_LINE.test(line)) continue
    const parts = line.split(BENEFIT_SPLIT).map((part) => part.trim()).filter(Boolean)
    const splittable = parts.length > 1 && parts.every((part) => part.length <= 8)
    for (const tag of splittable ? parts : [line]) {
      const key = tag.toLowerCase()
      if (seen.has(key)) continue
      seen.add(key)
      tags.push(tag)
    }
  }
  return tags
}

/** 高管介绍：采集形态为「姓名 / 职位 / 简介」；第二行不像短职位名时不拆，避免臆造。 */
export function parseExecutive(value: unknown): { name: string | null; title: string | null; bio: string[] } {
  const lines = sectionLines(value)
  if (lines.length === 0) return { name: null, title: null, bio: [] }
  const head = lines[0] ?? null
  const second = lines[1] ?? null
  const rest = lines.slice(2)
  const looksLikeTitle = second !== null && second.length <= 12 && !/[。！？，,；;]/.test(second)
  return {
    name: head,
    title: looksLikeTitle ? second : null,
    bio: second === null ? rest : looksLikeTitle ? rest : [second, ...rest],
  }
}

function SectionCard({ section }: { section: JdSection }) {
  const shape = sectionShape(section.items)
  return (
    <section className="section-card" title="本节标题与内容均取自该岗位 JD 原文，未做改写">
      <h3>{section.title}</h3>
      {shape === 'chips' ? (
        <div className="detail-tags">
          {section.items.map((item) => (
            <span key={item} className="tag-micro">{displayItem(item)}</span>
          ))}
        </div>
      ) : shape === 'paragraph' ? (
        <p className="section-paragraph">{displayItem(section.items[0] ?? '')}</p>
      ) : (
        <ol className="section-list">
          {section.items.map((item, index) => (
            <li key={`${section.title}-${index}`}>{displayItem(item)}</li>
          ))}
        </ol>
      )}
    </section>
  )
}

function FactTable({ rows }: { rows: readonly (readonly [string, string])[] }) {
  return (
    <table className="fact-table">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ArchiveBlock({ title, label = null, body }: {
  title: string
  label?: string | null
  body: ReactNode
}) {
  return (
    <details className="archive-block">
      <summary>
        <span>{title}</span>
        {label ? <span className="mono-label">{label}</span> : null}
      </summary>
      <div className="archive-body">{body}</div>
    </details>
  )
}

/** 公司档案：工作时间及福利 / 招聘官信息（可多位）/ 人才发展 / 高管介绍 / 公司介绍 / 工商信息。 */
export function CompanyArchive({ job, company }: { job: JobProfileJob; company: JobProfileCompany | null }) {
  const sections = company?.sections ?? {}
  const introLines = sectionLines(sections['intro'])
  const workTime = parseWorkTime(sections['benefits'])
  const benefitTags = parseBenefits(sections['benefits'])
  const talentLines = sectionLines(sections['talent'])
  const executive = parseExecutive(sections['executives'])
  const businessRows = parseBusinessRows(sections['business'])
  const benefitLabel = [workTime, benefitTags.length > 0 ? `${benefitTags.length} 项福利` : null]
    .filter((part): part is string => Boolean(part))
    .join(' · ')

  // 招聘官：本职位招聘官（job 字段）在前，公司页「招聘Boss」区块解析出的其他招聘官在后，按姓名去重。
  const recruiters: Recruiter[] = []
  if (job.boss_name) {
    recruiters.push({ name: job.boss_name, title: null, note: job.active_time, current: true })
  }
  for (const person of parseBosses(sections['bosses'])) {
    if (recruiters.some((item) => item.name === person.name)) continue
    recruiters.push(person)
  }

  // 没有采到的分节整块不展示（不渲染空 summary）。
  return (
    <div className="archive">
      {workTime || benefitTags.length > 0 ? (
        <ArchiveBlock
          title="工作时间及福利"
          label={benefitLabel || null}
          body={
            benefitTags.length > 0 ? (
              <div className="detail-tags">
                {benefitTags.map((tag) => <span key={tag} className="tag-micro">{tag}</span>)}
              </div>
            ) : (
              <p className="form-message">公司页未采到福利项目。</p>
            )
          }
        />
      ) : null}

      {recruiters.length > 0 ? (
        <ArchiveBlock
          title="招聘官信息"
          label={recruiters.length > 1 ? `${recruiters.length} 位招聘官` : recruiters[0]?.name ?? null}
          body={
            <div className="recruiter-list">
              {recruiters.map((person, index) => (
                <div key={`${person.name}-${index}`} className="recruiter-item">
                  <div className="recruiter-id">
                    <strong>{person.name}</strong>
                    {person.title ? <span className="recruiter-title">{person.title}</span> : null}
                    {person.current ? (
                      <span className="mono-label">本职位{person.note ? ` · ${person.note}` : ''}</span>
                    ) : null}
                  </div>
                  {!person.current && person.note ? <p className="recruiter-note">{person.note}</p> : null}
                </div>
              ))}
            </div>
          }
        />
      ) : null}

      {talentLines.length > 0 ? (
        <ArchiveBlock
          title="人才发展"
          body={
            talentLines.every((line) => line.length <= 14) ? (
              <div className="detail-tags">
                {talentLines.map((line) => <span key={line} className="tag-micro">{line}</span>)}
              </div>
            ) : (
              <ul className="section-list">
                {talentLines.map((line, index) => <li key={`talent-${index}`}>{line}</li>)}
              </ul>
            )
          }
        />
      ) : null}

      {executive.name ? (
        <ArchiveBlock
          title="高管介绍"
          body={
            <div className="executive">
              <div className="executive-id">
                <strong>{executive.name}</strong>
                {executive.title ? <span className="mono-label">{executive.title}</span> : null}
              </div>
              {executive.bio.length > 0 ? <p className="detail-text">{executive.bio.join('\n')}</p> : null}
            </div>
          }
        />
      ) : null}

      {introLines.length > 0 ? (
        <ArchiveBlock
          title="公司介绍"
          body={<p className="detail-text">{introLines.join('\n')}</p>}
        />
      ) : null}

      {businessRows.length > 0 ? (
        <ArchiveBlock title="工商信息" body={<FactTable rows={businessRows} />} />
      ) : null}
    </div>
  )
}

/** 岗位案卷：案卷头（含人工确认操作位）+ 岗位概览 + JD 分节卡。公司档案由页面挂到右栏。 */
export function JobDetailCard({
  job,
  company,
  onPromote,
  onDismiss,
  promotePending = false,
  dismissPending = false,
  confirmDismiss = false,
  actionMessage = null,
}: {
  job: JobProfileJob
  company: JobProfileCompany | null
  onPromote: () => void
  onDismiss: () => void
  promotePending?: boolean
  dismissPending?: boolean
  confirmDismiss?: boolean
  actionMessage?: { text: string; error: boolean } | null
}) {
  const sections = parseJdSections(job.jd_text)

  return (
    <article className="dossier" aria-label="岗位案卷">
      <header className="dossier-head">
        <div className="dossier-head-top">
          <h2>岗位案卷</h2>
          <button type="button" className="ghost" disabled title="收藏未接入">收藏</button>
        </div>
        <h3 className="dossier-title">{job.title ?? job.ext_id}</h3>
        <div className="dossier-origin">
          <span>岗位来源：BOSS 直聘</span>
          <span className="mono-label">
            {job.detail_at ? `更新：${job.detail_at.slice(0, 10)}` : '详情页未补全'}
          </span>
        </div>
        <div className="dossier-actions">
          <button
            type="button"
            className="primary-action"
            onClick={onPromote}
            disabled={promotePending}
          >
            {promotePending ? '提交中…' : '添加到候选区'}
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={onDismiss}
            disabled={dismissPending}
          >
            {confirmDismiss ? '确认忽略（终态）' : '忽略'}
          </button>
          {PENDING_DOSSIER_ACTIONS.map((action) => (
            <button key={action.label} type="button" className="ghost" disabled title={action.reason}>
              {action.label}
            </button>
          ))}
        </div>
        {actionMessage ? (
          <p className={`form-message ${actionMessage.error ? 'error' : ''}`}>{actionMessage.text}</p>
        ) : null}
      </header>

      <section className="dossier-block">
        <h3>岗位概览</h3>
        <table className="overview-table">
          <tbody>
            <tr>
              <th scope="row">岗位名称</th><td>{job.title ?? '—'}</td>
              <th scope="row">公司名称</th><td>{job.company ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">工作地点</th>
              <td>{[job.city, job.district].filter(Boolean).join(' ') || '—'}</td>
              <th scope="row">薪资范围</th><td>{job.salary_text ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">经验要求</th><td>{job.exp_text ?? '—'}</td>
              <th scope="row">学历要求</th><td>{job.degree ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">所属行业</th><td>{job.industry ?? '—'}</td>
              <th scope="row">融资阶段</th><td>{job.stage ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">公司规模</th><td>{job.scale ?? '—'}</td>
              <th scope="row">办公地址</th><td>{job.address ?? '—'}</td>
            </tr>
          </tbody>
        </table>
      </section>

      {sections.length > 0 ? (
        sections.map((section, index) => (
          <SectionCard key={`${section.title}-${index}`} section={section} />
        ))
      ) : (
        <section className="dossier-block">
          <h3>职位详情</h3>
          <p className="form-message">详情页尚未补全 JD 原文；入池后自动排队抓取。</p>
        </section>
      )}
    </article>
  )
}