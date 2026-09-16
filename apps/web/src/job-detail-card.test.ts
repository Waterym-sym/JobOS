import { describe, expect, it } from 'vitest'

import {
  parseBenefits,
  parseBosses,
  parseBusinessRows,
  parseExecutive,
  parseWorkTime,
  sectionLines,
  splitNameTitle,
} from './job-detail-card'

describe('sectionLines', () => {
  it('剔除采集夹带的整行控件文案，正文不动', () => {
    const raw = '一家靠谱落地的公司\n展开\n点击查看地图'
    expect(sectionLines(raw)).toEqual(['一家靠谱落地的公司'])
  })

  it('非字符串与空串返回空数组', () => {
    expect(sectionLines(null)).toEqual([])
    expect(sectionLines(123)).toEqual([])
    expect(sectionLines('   ')).toEqual([])
  })
})

describe('parseBusinessRows', () => {
  it('把「标签行 + 下一行值」的工商原文解析成表格行', () => {
    const raw = [
      '查看更多信息',
      '企业名称：',
      '天星橙（杭州）人工智能有限公司',
      '法定代表人：',
      '杨淅超',
      '成立时间：',
      '2026-09-09',
      '注册资本：',
      '-',
      '经营范围：',
      '一般项目：人工智能应用软件开发；技术服务。',
    ].join('\n')
    const rows = parseBusinessRows(raw)
    expect(rows).toEqual([
      ['企业名称', '天星橙（杭州）人工智能有限公司'],
      ['法定代表人', '杨淅超'],
      ['成立时间', '2026-09-09'],
      ['注册资本', '-'],
      ['经营范围', '一般项目：人工智能应用软件开发；技术服务。'],
    ])
  })

  it('支持标签与值同一行的形态，无法配对的行不展示', () => {
    const rows = parseBusinessRows('孤立行无标签\n经营状态：开业')
    expect(rows).toEqual([['经营状态', '开业']])
  })
})

describe('splitNameTitle', () => {
  it.each([
    ['张女士hr', '张女士', 'hr'],
    ['姜先生HR', '姜先生', 'HR'],
    ['陈金朋高级营销总监', '陈金朋', '高级营销总监'],
    ['王玮上海总部总经理', '王玮', '上海总部总经理'],
    ['焦先生创始人兼COO', '焦先生', '创始人兼COO'],
    ['苏女士人事经理HRBP', '苏女士', '人事经理HRBP'],
    ['沈明航招聘者', '沈明航', '招聘者'],
  ])('%s → 姓名 %s / 职位 %s', (line, name, title) => {
    expect(splitNameTitle(line)).toEqual({ name, title })
  })

  it('识别不出职位词头时整行作为姓名，不臆造', () => {
    expect(splitNameTitle('***')).toEqual({ name: '***', title: null })
  })
})

describe('parseBosses', () => {
  it('解析多位招聘官，切分姓名/职位并保留在招职位行', () => {
    const raw = [
      '陈金朋高级营销总监',
      '正在招聘 “兼职·FDE全国招募” 等职位',
      '黄女士招聘经理',
      '正在招聘 “电商总监” 等职位',
      '赵先生HR',
      '正在招聘 “外贸跟单实习生” 等职位',
      '查看所有职位',
    ].join('\n')
    const people = parseBosses(raw)
    expect(people).toHaveLength(3)
    expect(people[0]).toMatchObject({ name: '陈金朋', title: '高级营销总监', current: false })
    expect(people[0]?.note).toContain('FDE全国招募')
    expect(people[1]).toMatchObject({ name: '黄女士', title: '招聘经理' })
    expect(people[2]).toMatchObject({ name: '赵先生', title: 'HR' })
  })

  it('不符合两行结构的行跳过', () => {
    expect(parseBosses('只有一行没有在招描述')).toEqual([])
  })
})

describe('parseWorkTime', () => {
  it('取含上下班时刻的原文行作为工作时间摘要', () => {
    const raw = '上午09:00 - 下午06:00\n排班轮休、偶尔加班\n交通补助'
    expect(parseWorkTime(raw)).toBe('上午09:00 - 下午06:00')
  })

  it('没有时刻行返回 null', () => {
    expect(parseWorkTime('双休\n五险一金')).toBeNull()
    expect(parseWorkTime(null)).toBeNull()
  })
})

describe('parseBenefits', () => {
  it('去掉上下班时刻行，其余拆成福利标签并去重', () => {
    const raw = [
      '上午09:00 - 下午06:00',
      '双休、偶尔加班',
      '交通补助',
      '生日福利',
      '五险一金',
      '生日福利',
    ].join('\n')
    expect(parseBenefits(raw)).toEqual([
      '双休', '偶尔加班', '交通补助', '生日福利', '五险一金',
    ])
  })

  it('没有时刻行时正常；长句不强行拆分', () => {
    const raw = '双休\n提供具有市场竞争力的薪酬和年终奖与项目分成'
    expect(parseBenefits(raw)).toEqual(['双休', '提供具有市场竞争力的薪酬和年终奖与项目分成'])
  })
})

describe('parseExecutive', () => {
  it('按 姓名/职位/简介 拆分高管介绍，去掉展开噪声', () => {
    const raw = '王玉林\nCEO\n现任魔筷科技CEO，供职阿里巴巴。\n展开'
    const parsed = parseExecutive(raw)
    expect(parsed.name).toBe('王玉林')
    expect(parsed.title).toBe('CEO')
    expect(parsed.bio).toEqual(['现任魔筷科技CEO，供职阿里巴巴。'])
  })

  it('第二行不像短职位名时不拆，避免臆造', () => {
    const parsed = parseExecutive('夏洛克\n袁航（Sherlock）认知神经科学研究者。')
    expect(parsed.name).toBe('夏洛克')
    expect(parsed.title).toBeNull()
    expect(parsed.bio).toEqual(['袁航（Sherlock）认知神经科学研究者。'])
  })

  it('空内容返回空结构', () => {
    expect(parseExecutive(null)).toEqual({ name: null, title: null, bio: [] })
  })
})
