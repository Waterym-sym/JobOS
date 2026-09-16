import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { CompanyArchive, JobDetailCard } from './job-detail-card'
import { jdKeywords } from './lib/jd-sections'
import {
  dismissScreeningEntry,
  fetchJobProfile,
  fetchScreeningEntries,
  promoteScreeningEntry,
  revertScreeningEntry,
  type ScreeningEntryItem,
} from './lib/capture'

/** 评分维度仅在契约（ARCH-MATCH-001）里存在；引擎未接入前只列标签、不给分数。 */
const ASSESS_DIMENSIONS = ['技能匹配', '经验匹配', '学历匹配', '薪资匹配', '行业匹配'] as const

function entryLabel(entry: ScreeningEntryItem): string {
  return entry.title ?? entry.ext_id
}

function enteredAt(entry: ScreeningEntryItem): string {
  return entry.entered_at ? entry.entered_at.slice(5, 16).replace('T', ' ') : '—'
}

function EmptyPool() {
  return (
    <div className="empty-state">
      <span className="empty-rule" aria-hidden="true" />
      <h2>筛选池为空</h2>
      <p>岗位池里补全完成的岗位会自动流入这里；先在岗位池导入岗位列表并人工入池。</p>
      <a className="text-action" href="#/jobs">前往岗位池</a>
    </div>
  )
}

export function ScreeningPage() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [confirmDismiss, setConfirmDismiss] = useState(false)
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)

  const entries = useQuery({
    queryKey: ['screening-entries', 'screened'],
    queryFn: ({ signal }) => fetchScreeningEntries('screened', signal),
    refetchInterval: 6000,
  })
  const items = entries.data ?? []
  const selected = items.find((item) => item.id === selectedId) ?? null

  // 选中项消失（推进/忽略）时回到最新一条；空则清空。
  useEffect(() => {
    if (!items.some((item) => item.id === selectedId)) {
      setSelectedId(items[0]?.id ?? null)
    }
  }, [items, selectedId])

  useEffect(() => setConfirmDismiss(false), [selectedId])

  const profile = useQuery({
    queryKey: ['job-profile', selected?.ext_id],
    queryFn: ({ signal }) => fetchJobProfile(selected?.ext_id ?? '', signal),
    enabled: Boolean(selected),
    refetchInterval: 6000,
  })

  const promote = useMutation({
    mutationFn: promoteScreeningEntry,
    onSuccess: (entry) => {
      setMessage({ text: `已进入候选区：${entryLabel(entry)}`, error: false })
      void queryClient.invalidateQueries({ queryKey: ['screening-entries'] })
    },
    onError: (error: Error) => setMessage({ text: error.message, error: true }),
  })
  const dismiss = useMutation({
    mutationFn: dismissScreeningEntry,
    onSuccess: (entry) => {
      setMessage({ text: `已忽略：${entryLabel(entry)}（记录保留，可审计）`, error: false })
      void queryClient.invalidateQueries({ queryKey: ['screening-entries'] })
    },
    onError: (error: Error) => setMessage({ text: error.message, error: true }),
  })

  const keywords = profile.data
    ? jdKeywords(profile.data.job.jd_text, profile.data.job.skill_tags)
    : []

  async function copyKeywords() {
    try {
      await navigator.clipboard.writeText(keywords.join('、'))
      setMessage({ text: `已复制 ${keywords.length} 个关键词`, error: false })
    } catch {
      setMessage({ text: '复制失败：浏览器未授权剪贴板', error: true })
    }
  }

  // 忽略为终态操作：第一次点击进入确认，第二次才真正提交。
  function handleDismiss() {
    if (!selected) return
    if (confirmDismiss) dismiss.mutate(selected.id)
    else setConfirmDismiss(true)
  }

  if (!entries.isPending && items.length === 0) {
    return <EmptyPool />
  }

  return (
    <>
      <div className="screening-split">
        <section className="screening-main" aria-label="职位详情">
          {entries.isPending ? <p className="form-message">读取筛选池…</p> : null}
          {!entries.isPending && !selected ? <p className="form-message">暂无可展示的岗位。</p> : null}
          {selected && profile.isPending ? <p className="form-message">读取岗位画像…</p> : null}
          {profile.isError ? <p className="form-message error">{(profile.error as Error).message}</p> : null}
          {selected && profile.data ? (
            <JobDetailCard
              job={profile.data.job}
              company={profile.data.company}
              onPromote={() => promote.mutate(selected.id)}
              onDismiss={handleDismiss}
              promotePending={promote.isPending}
              dismissPending={dismiss.isPending}
              confirmDismiss={confirmDismiss}
              actionMessage={message}
            />
          ) : null}
        </section>

        <aside className="screening-assess" aria-label="AI 建议、关键词与公司档案">
          <section className="assess-panel" aria-labelledby="assess-heading">
            <div className="assess-head">
              <div>
                <p className="mono-label">ASSESS · 未接入</p>
                <h2 id="assess-heading">AI 建议与评分</h2>
              </div>
              <button type="button" className="ghost" disabled title="评分引擎未接入">重新分析</button>
            </div>
            <div className="assess-score">
              <div className="assess-ring" aria-hidden="true">
                <span>○</span>
                <strong>待评分</strong>
              </div>
              <div className="assess-dims">
                {ASSESS_DIMENSIONS.map((dimension) => (
                  <div key={dimension} className="assess-dim">
                    <span>{dimension}</span>
                    <span className="assess-track" aria-hidden="true" />
                    <span className="mono-label">—</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="form-message">
              评分引擎未接入：Prompt 与权重需人工评审后另行实现，这里不会自动生成分数。
            </p>
          </section>

          <section className="assess-panel" aria-labelledby="keywords-heading">
            <div className="assess-head">
              <div>
                <p className="mono-label">KEYWORDS · 有原文依据</p>
                <h2 id="keywords-heading">匹配关键词</h2>
              </div>
              <button
                type="button"
                className="ghost"
                onClick={() => void copyKeywords()}
                disabled={keywords.length === 0}
              >
                复制全部
              </button>
            </div>
            {keywords.length > 0 ? (
              <div className="detail-tags">
                {keywords.map((keyword) => <span key={keyword} className="tag-micro">{keyword}</span>)}
              </div>
            ) : (
              <p className="form-message">
                {profile.isPending ? '读取中…' : '该岗位 JD 原文里未匹配到常见关键词。'}
              </p>
            )}
          </section>

          {selected && profile.data ? (
            <CompanyArchive job={profile.data.job} company={profile.data.company} />
          ) : null}
        </aside>
      </div>
    </>
  )
}

export function CandidatesPage() {
  const queryClient = useQueryClient()
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)

  const candidates = useQuery({
    queryKey: ['screening-entries', 'candidate'],
    queryFn: ({ signal }) => fetchScreeningEntries('candidate', signal),
    refetchInterval: 6000,
  })
  const revert = useMutation({
    mutationFn: revertScreeningEntry,
    onSuccess: (entry) => {
      setMessage({ text: `已退回筛选池：${entryLabel(entry)}`, error: false })
      void queryClient.invalidateQueries({ queryKey: ['screening-entries'] })
    },
    onError: (error: Error) => setMessage({ text: error.message, error: true }),
  })

  const items = candidates.data ?? []
  if (!candidates.isPending && items.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-rule" aria-hidden="true" />
        <h2>还没有候选岗位</h2>
        <p>候选区是进入投递准备的唯一入口；先在筛选池逐条人工确认，系统不会自动推进。</p>
        <a className="text-action" href="#/screening">前往筛选池</a>
      </div>
    )
  }

  return (
    <section className="sheet" aria-labelledby="candidates-heading">
      <div className="sheet-heading">
        <div>
          <p className="mono-label">SHORTLIST · 唯一投递入口</p>
          <h2 id="candidates-heading">候选岗位</h2>
        </div>
        <span className={`status-pill ${items.length ? 'confirmed' : 'neutral'}`}>
          <span aria-hidden="true">{items.length ? '●' : '○'}</span>候选 {items.length}
        </span>
      </div>
      <div className="sheet-body">
        {candidates.isPending ? (
          <p className="form-message">读取中…</p>
        ) : (
          <table className="raw-table">
            <thead>
              <tr><th>职位</th><th>公司</th><th>薪资</th><th>城市</th><th>进入时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{entryLabel(item)}</td>
                  <td>{item.company ?? '—'}</td>
                  <td>{item.salary_text ?? '—'}</td>
                  <td>{item.city ?? '—'}</td>
                  <td className="mono">{enteredAt(item)}</td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => revert.mutate(item.id)}
                      disabled={revert.isPending}
                    >
                      退回筛选池
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="form-message">投递包、三形态简历与招呼语仍未接入；本页只做人工候选决策。</p>
        {message ? <p className={`form-message ${message.error ? 'error' : ''}`}>{message.text}</p> : null}
      </div>
    </section>
  )
}