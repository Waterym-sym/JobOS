import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { JobProfileView } from './job-profile-view'
import {
  addToPool,
  fetchEnrichQueue,
  fetchJobProfile,
  fetchRawJobs,
  fetchShortlist,
  removeFromPool,
  resumeEnrich,
  type EnrichQueueStatus,
  type RawJobItem,
  type ShortlistItem,
} from './lib/capture'
import { degreeDisplay, expDisplay, monthlySalaryK, salaryDisplay } from './lib/job-display'

const SALARY_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部薪资' },
  { value: '10', label: '≥10K·月' },
  { value: '15', label: '≥15K·月' },
  { value: '20', label: '≥20K·月' },
  { value: '30', label: '≥30K·月' },
  { value: 'daily', label: '日薪·实习' },
]

const ENRICH_LABEL: Record<string, string> = {
  pending: '待补全',
  detail_done: '详情已到',
  done: '已补全',
  failed: '补全失败',
  screened: '已入筛选池',
  candidate: '已入候选区',
  dismissed: '已忽略',
}

const STAGE_LABEL: Record<string, string> = {
  detail: '详情页',
  company: '公司页',
}

// 补全完成（详情+公司页）后岗位已离开岗位池、流入后续漏斗，采集中心不再提供入池动作。
const SCREENING_TAG: Record<string, string> = {
  screened: '已入筛选池',
  candidate: '已入候选区',
  dismissed: '已忽略',
}

function EnrichBadge({ state }: { state: string }) {
  const symbol = state === 'done' || state === 'screened' || state === 'candidate' ? '●' : state === 'detail_done' ? '' : '○'
  return (
    <span className={`enrich-badge ${state}`}>
      <span aria-hidden="true">{symbol}</span>
      {ENRICH_LABEL[state] ?? state}
    </span>
  )
}

function QueueStrip({
  queue,
  onResume,
  isResuming,
}: {
  queue: EnrichQueueStatus
  onResume: () => void
  isResuming: boolean
}) {
  if (queue.paused) {
    return (
      <div className="queue-strip paused">
        <span className="evidence-symbol" aria-hidden="true">○</span>
        <div>
          <strong>补全已暂停</strong>
          <p>{queue.paused_reason ?? '需要人工确认后才会继续。'}</p>
        </div>
        <button type="button" className="ghost" onClick={onResume} disabled={isResuming}>
          {isResuming ? '恢复中…' : '人工恢复队列'}
        </button>
      </div>
    )
  }
  if (queue.running) {
    return (
      <div className="queue-strip">
        <span className="evidence-symbol confirmed" aria-hidden="true">◐</span>
        <div>
          <strong>正在补全</strong>
          <p>
            <code>{queue.running.ext_id}</code> · {STAGE_LABEL[queue.running.stage ?? ''] ?? '准备中'}
          </p>
          {queue.blocked_reason ? <p className="form-message error">{queue.blocked_reason}</p> : null}
        </div>
        <span className="tag-micro">待处理 {queue.pending.length}</span>
      </div>
    )
  }
  return (
    <div className="queue-strip">
      <span className="evidence-symbol" aria-hidden="true">○</span>
      <div>
        <strong>队列空闲</strong>
        <p>入池后自动排队：详情页 → 公司页；节流 ≥1800ms、并发恒 1。</p>
        {queue.blocked_reason ? <p className="form-message error">{queue.blocked_reason}</p> : null}
      </div>
      {queue.pending.length > 0 ? <span className="tag-micro">待处理 {queue.pending.length}</span> : null}
    </div>
  )
}

function JobDetailPanel({
  extId,
  poolItem,
  onClose,
}: {
  extId: string
  poolItem: ShortlistItem | undefined
  onClose: () => void
}) {
  const query = useQuery({
    queryKey: ['job-profile', extId],
    queryFn: ({ signal }) => fetchJobProfile(extId, signal),
    refetchInterval: 6000,
  })
  const job = query.data?.job
  const company = query.data?.company

  return (
    <aside className="job-detail" aria-label="岗位详情面板">
      <div className="job-detail-head">
        <div>
          <p className="mono-label">DETAIL · 本机数据</p>
          <h3>{job?.title ?? extId}</h3>
          <p className="detail-sub">
            {[job?.company, job?.city, job?.district].filter(Boolean).join(' · ') || '—'}
          </p>
        </div>
        <div className="job-detail-tools">
          {poolItem ? (
            <EnrichBadge state={poolItem.enrich_state} />
          ) : (
            <span className="tag-micro">未入池</span>
          )}
          <button type="button" className="ghost" onClick={onClose}>关闭（Esc）</button>
        </div>
      </div>

      {query.isPending ? <p className="form-message">读取中…</p> : null}
      {query.isError ? <p className="form-message error">{(query.error as Error).message}</p> : null}
      {poolItem?.failure_reason ? (
        <p className="form-message error">补全失败：{poolItem.failure_reason}</p>
      ) : null}

      {job ? <JobProfileView job={job} company={company ?? null} /> : null}
    </aside>
  )
}

function JobsTable({
  jobs,
  poolByExtId,
  onAdd,
  addingExtId,
  selectedExtId,
  onSelect,
}: {
  jobs: RawJobItem[]
  poolByExtId: Map<string, ShortlistItem>
  onAdd: (extId: string) => void
  addingExtId: string | null
  selectedExtId: string | null
  onSelect: (extId: string) => void
}) {
  const [keyword, setKeyword] = useState('')
  const [city, setCity] = useState('')
  const [degree, setDegree] = useState('')
  const [expFilter, setExpFilter] = useState('')
  const [salary, setSalary] = useState('')
  const [hidePooled, setHidePooled] = useState(false)

  const cities = useMemo(
    () => Array.from(new Set(jobs.map((job) => job.city).filter((value): value is string => Boolean(value)))).sort(),
    [jobs],
  )
  // 经验口径取自实际数据（含「5天/周」等实习口径），「不限」排最前。
  const expOptions = useMemo(() => {
    const values = Array.from(new Set(jobs.map((job) => expDisplay(job)).filter((value) => value && value !== '—')))
    return values.sort((a, b) => (a === '不限' ? -1 : b === '不限' ? 1 : a.localeCompare(b, 'zh')))
  }, [jobs])
  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase()
    const salaryFloor = salary && salary !== 'daily' ? Number(salary) : null
    return jobs.filter((job) => {
      // 「只看未入池」同时隐藏已在池中与已补全流入筛选池的岗位，只剩可操作项。
      if (hidePooled && (poolByExtId.has(job.ext_id) || job.screening_status)) return false
      if (city && job.city !== city) return false
      if (degree && (job.degree_code ?? '') !== degree) return false
      if (expFilter && expDisplay(job) !== expFilter) return false
      if (salary === 'daily') {
        if (job.salary_unit !== 'day' && job.salary_unit !== 'hour') return false
      } else if (salaryFloor !== null) {
        const monthlyK = monthlySalaryK(job)
        if (monthlyK === null || monthlyK < salaryFloor) return false
      }
      if (needle) {
        const haystack = `${job.title ?? ''} ${job.company ?? ''}`.toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return true
    })
  }, [jobs, poolByExtId, hidePooled, city, degree, expFilter, salary, keyword])

  return (
    <div className="sheet-body">
      <div className="filter-row">
        <div className="field">
          <label htmlFor="filter-keyword">关键字（职位 / 公司）</label>
          <input id="filter-keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="FDE、数据、平台…" />
        </div>
        <div className="field">
          <label htmlFor="filter-city">城市</label>
          <select id="filter-city" value={city} onChange={(event) => setCity(event.target.value)}>
            <option value="">全部</option>
            {cities.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-degree">学历</label>
          <select id="filter-degree" value={degree} onChange={(event) => setDegree(event.target.value)}>
            <option value="">全部</option>
            {Object.entries({ bachelor: '本科', master: '硕士', doctor: '博士', associate: '大专', unrestricted: '不限' }).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-exp">经验</label>
          <select id="filter-exp" value={expFilter} onChange={(event) => setExpFilter(event.target.value)}>
            <option value="">全部</option>
            {expOptions.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-salary">薪资</label>
          <select id="filter-salary" value={salary} onChange={(event) => setSalary(event.target.value)}>
            {SALARY_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>
        <label className="check-inline">
          <input type="checkbox" checked={hidePooled} onChange={(event) => setHidePooled(event.target.checked)} />
          只看未入池
        </label>
      </div>

      {jobs.length === 0 ? (
        <p className="form-message">尚无岗位。请先导入扩展导出的 JSON。</p>
      ) : (
        <>
          <table className="raw-table">
            <thead>
              <tr>
                <th>职位</th><th>公司</th><th>城市</th><th>薪资</th>
                <th>经验</th><th>学历</th><th>状态</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((job) => {
                const pooled = poolByExtId.get(job.ext_id)
                const flowedTag = job.screening_status
                  ? SCREENING_TAG[job.screening_status] ?? job.screening_status
                  : null
                return (
                  <tr
                    key={job.id}
                    className={selectedExtId === job.ext_id ? 'selected' : undefined}
                  >
                    <td>{job.title ?? '—'}</td>
                    <td>{job.company ?? '—'}</td>
                    <td>{job.city ?? '—'}{job.district ? ` · ${job.district}` : ''}</td>
                    <td>{salaryDisplay(job)}</td>
                    <td>{expDisplay(job)}</td>
                    <td>{degreeDisplay(job)}</td>
                    <td>
                      {job.screening_status ? (
                        <EnrichBadge state={job.screening_status} />
                      ) : pooled ? (
                        <EnrichBadge state={pooled.enrich_state} />
                      ) : (
                        <span className="form-message">未入池</span>
                      )}
                    </td>
                    <td>
                      <div className="row-actions">
                        {flowedTag ? (
                          <span className="tag-micro">{flowedTag}</span>
                        ) : pooled ? (
                          <span className="tag-micro">已入池</span>
                        ) : (
                          <button
                            type="button"
                            className="ghost btn-sm"
                            onClick={() => onAdd(job.ext_id)}
                            disabled={addingExtId === job.ext_id}
                          >
                            {addingExtId === job.ext_id ? '入池中…' : '加入岗位池'}
                          </button>
                        )}
                        <button
                          type="button"
                          className="ghost btn-sm"
                          onClick={() => onSelect(job.ext_id)}
                        >
                          查看
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="form-message">
            显示 {filtered.length} / {jobs.length} 条（列表上限 200 条，按时间倒序）。点击操作列的「查看」在右侧查看 JD 全文与公司画像。
          </p>
        </>
      )}
    </div>
  )
}

function PoolPanel({
  items,
  queue,
  onRemove,
  onResume,
  removingId,
  isResuming,
}: {
  items: ShortlistItem[]
  queue: EnrichQueueStatus
  onRemove: (id: string) => void
  onResume: () => void
  removingId: string | null
  isResuming: boolean
}) {
  return (
    <section className="sheet" aria-labelledby="pool-heading">
      <div className="sheet-heading">
        <div>
          <p className="mono-label">POOL · 入池即排队</p>
          <h2 id="pool-heading">岗位池与补全队列</h2>
        </div>
        <span className={`status-pill ${items.length ? 'confirmed' : 'neutral'}`}>
          <span aria-hidden="true">{items.length ? '●' : '○'}</span>
          池内 {items.length}
        </span>
      </div>

      <QueueStrip queue={queue} onResume={onResume} isResuming={isResuming} />

      {items.length === 0 ? (
        <div className="sheet-body">
          <p className="form-message">岗位池为空。在采集中心的「岗位列表与筛选」点击「加入岗位池」后会自动排队补全；补全完成的岗位自动流入筛选池，可在筛选池逐条判断。</p>
        </div>
      ) : (
        <div className="sheet-body">
          <table className="raw-table">
            <thead>
              <tr>
                <th>职位</th><th>公司</th><th>薪资</th><th>补全状态</th><th>入池时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.title ?? item.ext_id}</td>
                  <td>{item.company ?? '—'}</td>
                  <td>{item.salary_text ?? '—'}</td>
                  <td><EnrichBadge state={item.enrich_state} /></td>
                  <td className="mono">{item.added_at ? item.added_at.slice(5, 16).replace('T', ' ') : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="ghost danger"
                      onClick={() => onRemove(item.id)}
                      disabled={removingId === item.id}
                    >
                      {removingId === item.id ? '移出中…' : '移出'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/** 采集中心的「岗位列表与筛选」卡：浏览已导入岗位、人工入池，点击行看 JD 详情。 */
export function CaptureJobsSheet() {
  const queryClient = useQueryClient()
  const [actionMessage, setActionMessage] = useState<{ text: string; error: boolean } | null>(null)
  const [addingExtId, setAddingExtId] = useState<string | null>(null)
  const [selectedExtId, setSelectedExtId] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedExtId) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setSelectedExtId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedExtId])

  const rawJobs = useQuery({
    queryKey: ['raw-jobs'],
    queryFn: ({ signal }) => fetchRawJobs(signal),
    refetchInterval: 6000,
  })
  const pool = useQuery({
    queryKey: ['shortlist'],
    queryFn: ({ signal }) => fetchShortlist(signal),
    refetchInterval: 4000,
  })

  const poolByExtId = useMemo(
    () => new Map((pool.data ?? []).map((item) => [item.ext_id, item])),
    [pool.data],
  )

  const addMutation = useMutation({
    mutationFn: addToPool,
    onMutate: (extId: string) => setAddingExtId(extId),
    onSuccess: (item) => {
      setActionMessage({ text: `已入池：${item.title ?? item.ext_id} · 已排队补全`, error: false })
      void queryClient.invalidateQueries({ queryKey: ['shortlist'] })
      void queryClient.invalidateQueries({ queryKey: ['enrich-queue'] })
    },
    onError: (error: Error) => setActionMessage({ text: error.message, error: true }),
    onSettled: () => setAddingExtId(null),
  })

  return (
    <section className="sheet" aria-labelledby="jobs-heading">
      <div className="sheet-heading">
        <div>
          <p className="mono-label">JOBS · 导入数据</p>
          <h2 id="jobs-heading">岗位列表与筛选</h2>
        </div>
        <span className="status-pill neutral"><span aria-hidden="true">●</span>原始数据保留</span>
      </div>
      <div className={`jobs-split${selectedExtId ? ' with-detail' : ''}`}>
        <JobsTable
          jobs={rawJobs.data ?? []}
          poolByExtId={poolByExtId}
          onAdd={(extId) => addMutation.mutate(extId)}
          addingExtId={addingExtId}
          selectedExtId={selectedExtId}
          onSelect={setSelectedExtId}
        />
        {selectedExtId ? (
          <JobDetailPanel
            extId={selectedExtId}
            poolItem={poolByExtId.get(selectedExtId)}
            onClose={() => setSelectedExtId(null)}
          />
        ) : null}
      </div>
      {actionMessage ? (
        <div className="sheet-body">
          <p className={`form-message ${actionMessage.error ? 'error' : ''}`}>{actionMessage.text}</p>
        </div>
      ) : null}
    </section>
  )
}

/** 岗位池：只保留补全队列与池内岗位（岗位列表已移至采集中心）。 */
export function JobsPage() {
  const queryClient = useQueryClient()
  const [actionMessage, setActionMessage] = useState<{ text: string; error: boolean } | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)

  const pool = useQuery({
    queryKey: ['shortlist'],
    queryFn: ({ signal }) => fetchShortlist(signal),
    refetchInterval: 4000,
  })
  const queue = useQuery({
    queryKey: ['enrich-queue'],
    queryFn: ({ signal }) => fetchEnrichQueue(signal),
    refetchInterval: 3000,
  })

  const removeMutation = useMutation({
    mutationFn: removeFromPool,
    onMutate: (id: string) => setRemovingId(id),
    onSuccess: (item) => {
      setActionMessage({ text: `已移出岗位池：${item.title ?? item.ext_id}`, error: false })
      void queryClient.invalidateQueries({ queryKey: ['shortlist'] })
      void queryClient.invalidateQueries({ queryKey: ['enrich-queue'] })
    },
    onError: (error: Error) => setActionMessage({ text: error.message, error: true }),
    onSettled: () => setRemovingId(null),
  })
  const resumeMutation = useMutation({
    mutationFn: resumeEnrich,
    onSuccess: (status) => {
      setActionMessage({
        text: status.paused ? '仍处于暂停状态，请检查扩展与页面风控。' : '补全队列已恢复。',
        error: status.paused,
      })
      void queryClient.invalidateQueries({ queryKey: ['enrich-queue'] })
    },
    onError: (error: Error) => setActionMessage({ text: error.message, error: true }),
  })

  return (
    <div className="sheet-stack">
      <PoolPanel
        items={pool.data ?? []}
        queue={queue.data ?? { paused: false, paused_reason: null, running: null, pending: [] }}
        onRemove={(id) => removeMutation.mutate(id)}
        onResume={() => resumeMutation.mutate()}
        removingId={removingId}
        isResuming={resumeMutation.isPending}
      />

      {actionMessage ? (
        <p className={`form-message ${actionMessage.error ? 'error' : ''}`}>{actionMessage.text}</p>
      ) : null}
    </div>
  )
}