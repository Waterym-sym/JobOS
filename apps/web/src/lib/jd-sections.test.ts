import { describe, expect, it } from 'vitest'

import { displayItem, jdKeywords, parseJdSections, sectionShape } from './jd-sections'

const SAMPLE_JD = `我们是一家在杭州落地的 AI 企业服务公司，已经服务 60 多家企业，涉及 8 个行业。
目前业务方向是：面向中小企业做 AI 落地服务。
岗位职责
负责客户现场的 AI 应用需求梳理与方案设计
负责 Dify / Coze 智能体搭建与交付
任职要求：
本科及以上学历，3 年以上相关经验
熟悉 Python 与 API 集成
加分项
有 n8n 或知识库项目经验`

describe('parseJdSections', () => {
  it('keeps the leading paragraph as 职位简介 and cuts sections from the JD itself', () => {
    const sections = parseJdSections(SAMPLE_JD)

    expect(sections.map((section) => section.title)).toEqual([
      '职位简介',
      '岗位职责',
      '任职要求',
      '加分项',
    ])
    expect(sections[0]?.items).toHaveLength(2)
    expect(sections[1]?.items).toHaveLength(2)
    expect(sections[2]?.items[1]).toBe('熟悉 Python 与 API 集成')
    expect(sections[3]?.items).toEqual(['有 n8n 或知识库项目经验'])
  })

  it('keeps every line when the JD has no detectable headings', () => {
    const sections = parseJdSections('负责一线交付。\n与客户沟通需求。')

    expect(sections).toHaveLength(1)
    expect(sections[0]?.title).toBe('职位简介')
    expect(sections[0]?.items).toEqual(['负责一线交付。', '与客户沟通需求。'])
  })

  it('does not mistake bullets for headings', () => {
    const long = 'x'.repeat(40)
    const sections = parseJdSections(`岗位职责\n- 负责交付\n1. 负责沟通\n${long}`)

    expect(sections.map((section) => section.title)).toEqual(['岗位职责'])
    // 编号保留在条目原文里（展示层剥离）；破折号 bullet 原样保留。
    expect(sections[0]?.items).toEqual(['- 负责交付', '1. 负责沟通', long])
  })

  it('cuts inline headings and numbered items from a single-line BOSS JD', () => {
    const jd =
      '岗位职责1、深入跨境电商一线，梳理 AI 场景。2、负责从 0 到 1 落地。' +
      '任职要求1、本科及以上学历，有 1-3 年经验。2、熟悉 Python 3.10 与 Prompt。' +
      '加分项\n有电商经验优先。'
    const sections = parseJdSections(jd)

    expect(sections.map((section) => section.title)).toEqual(['岗位职责', '任职要求', '加分项'])
    expect(sections[0]?.items).toEqual(['1、深入跨境电商一线，梳理 AI 场景。', '2、负责从 0 到 1 落地。'])
    expect(sections[1]?.items).toEqual([
      '1、本科及以上学历，有 1-3 年经验。',
      '2、熟悉 Python 3.10 与 Prompt。',
    ])
    expect(sections[2]?.items).toEqual(['有电商经验优先。'])
  })

  it('displayItem strips only the leading numbering, never body digits', () => {
    expect(displayItem('1、深入一线梳理 AI 场景。')).toBe('深入一线梳理 AI 场景。')
    expect(displayItem('2. 熟悉 Python 3.10。')).toBe('熟悉 Python 3.10。')
    expect(displayItem('（3）有 1-3 年经验。')).toBe('有 1-3 年经验。')
    expect(displayItem('无编号条目 2026 保持原样')).toBe('无编号条目 2026 保持原样')
  })

  it('normalizes list prefixes and trailing colons out of titles', () => {
    const sections = parseJdSections('一、岗位职责：\n交付 AI 项目\n2. 任职要求\n本科')
    expect(sections.map((section) => section.title)).toEqual(['岗位职责', '任职要求'])
  })

  it('returns nothing for an empty JD', () => {
    expect(parseJdSections(null)).toEqual([])
    expect(parseJdSections('   \n  ')).toEqual([])
  })
})

describe('sectionShape', () => {
  it('renders short items as chips (加分项 这类词表)', () => {
    expect(sectionShape(['人工智能', '计算机软件'])).toBe('chips')
  })

  it('renders a single long item as a paragraph (合作方式 这类说明)', () => {
    expect(sectionShape(['前期以项目制合作为主，入企诊断调研，由公司负责获客。'])).toBe('paragraph')
  })

  it('renders several long items as a numbered list', () => {
    expect(sectionShape(['了解大模型、Prompt、RAG、知识库、智能体、API 调用；', '能独立做出可演示的 Demo；'])).toBe('list')
  })
})

describe('jdKeywords', () => {
  it('keeps only keywords that really appear in the JD or come from skill tags', () => {
    const keywords = jdKeywords(SAMPLE_JD, ['TypeScript'])

    expect(keywords).toContain('Dify')
    expect(keywords).toContain('n8n')
    expect(keywords).toContain('Python')
    expect(keywords).toContain('API')
    expect(keywords).toContain('智能体')
    expect(keywords).toContain('知识库')
    expect(keywords).toContain('TypeScript')
    // 原文里没有的不猜。
    expect(keywords).not.toContain('Kubernetes')
    expect(keywords).not.toContain('Vue')
  })

  it('does not match hints inside longer ascii words', () => {
    const keywords = jdKeywords('object storage service', [])

    expect(keywords).not.toContain('RAG')
    expect(keywords).not.toContain('API')
  })

  it('deduplicates and caps the list', () => {
    const keywords = jdKeywords(`${SAMPLE_JD}\nDify 与 DIFY`, [])
    const lower = keywords.map((keyword) => keyword.toLowerCase())

    expect(new Set(lower).size).toBe(lower.length)
    expect(keywords.length).toBeLessThanOrEqual(18)
  })
})