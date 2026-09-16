import type { JobProfileCompany, JobProfileJob } from './lib/capture'

const COMPANY_SECTION_LABEL: Record<string, string> = {
  intro: '公司介绍',
  talent: '人才发展',
  benefits: '工作时间及福利',
  products: '产品介绍',
  business: '工商信息',
  address: '公司地址',
  executives: '高管介绍',
  bosses: '招聘 Boss',
}

/** 公司分节只呈现文本证据；未知形状不猜测、不渲染。 */
function sectionText(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (Array.isArray(value)) {
    const lines = value.filter(
      (item): item is string => typeof item === 'string' && Boolean(item.trim()),
    )
    return lines.length ? lines.join('\n') : null
  }
  return null
}

/** 公司分节：可选 keys 过滤（公司信息 / 工商信息分组）；只呈现文本证据，未知形状不猜测。 */
export function CompanySections({
  sections,
  keys,
}: {
  sections: Record<string, unknown>
  keys?: readonly string[]
}) {
  const source = keys ? Object.entries(sections).filter(([key]) => keys.includes(key)) : Object.entries(sections)
  const entries = source
    .map(([key, value]) => [key, sectionText(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null)
  if (entries.length === 0) {
    return <p className="form-message">公司页未采到分节内容（页面结构可能变化，需人工复核）。</p>
  }
  return (
    <div className="detail-sections">
      {entries.map(([key, text]) => (
        <section key={key}>
          <p className="mono-label">{COMPANY_SECTION_LABEL[key] ?? key}</p>
          <p className="detail-text">{text}</p>
        </section>
      ))}
    </div>
  )
}

/** 岗位画像正文：事实表 + 技能标签 + JD 全文 + 公司画像（岗位池详情抽屉共用）。 */
export function JobProfileView({
  job,
  company,
}: {
  job: JobProfileJob
  company: JobProfileCompany | null
}) {
  return (
    <>
      <dl className="detail-facts">
        <div><dt>薪资</dt><dd>{job.salary_text ?? '—'}</dd></div>
        <div><dt>经验</dt><dd>{job.exp_text ?? '—'}</dd></div>
        <div><dt>学历</dt><dd>{job.degree ?? '—'}</dd></div>
        <div><dt>行业</dt><dd>{job.industry ?? '—'}</dd></div>
        <div><dt>融资阶段</dt><dd>{job.stage ?? '—'}</dd></div>
        <div><dt>公司规模</dt><dd>{job.scale ?? '—'}</dd></div>
        <div className="full"><dt>办公地址</dt><dd>{job.address ?? '—'}</dd></div>
        <div className="full">
          <dt>招聘官</dt>
          <dd>{job.boss_name ?? '—'}{job.active_time ? ` · ${job.active_time}` : ''}</dd>
        </div>
      </dl>

      {job.skill_tags.length > 0 ? (
        <div className="detail-tags">
          {job.skill_tags.map((tag) => <span key={tag} className="tag-micro">{tag}</span>)}
        </div>
      ) : null}

      <section className="detail-block">
        <p className="mono-label">
          JD 全文{job.detail_at ? ` · 详情页 ${job.detail_at.slice(5, 16).replace('T', ' ')}` : ''}
        </p>
        {job.jd_text ? (
          <div className="jd-text">{job.jd_text}</div>
        ) : (
          <p className="form-message">详情页尚未补全；入池后自动排队抓取。</p>
        )}
      </section>

      <section className="detail-block">
        <p className="mono-label">公司画像{company?.name ? ` · ${company.name}` : ''}</p>
        {company ? (
          <CompanySections sections={company.sections ?? {}} />
        ) : (
          <p className="form-message">公司页尚未补全；详情页完成后自动抓取。</p>
        )}
      </section>
    </>
  )
}