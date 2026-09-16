export const DEGREE_LABEL: Record<string, string> = {
  bachelor: '本科',
  associate: '大专',
  master: '硕士',
  doctor: '博士',
  secondary: '中专/高中',
  unrestricted: '不限',
}

const SALARY_UNIT_LABEL: Record<string, string> = {
  month_K: 'K·月',
  month_yuan: '元·月',
  day: '元·天',
  hour: '元·时',
  year: '万·年',
}

export function salaryDisplay(job: {
  low_salary: number | null
  high_salary: number | null
  salary_unit: string
  salary_text: string | null
}): string {
  if (job.low_salary == null && job.high_salary == null) return job.salary_text ?? '—'
  const unit = SALARY_UNIT_LABEL[job.salary_unit] ?? ''
  const low = job.low_salary ?? '—'
  const high = job.high_salary ?? '—'
  return `${low}-${high}${unit ? ` ${unit}` : ''}`
}

/** 归一化月薪下限为 K（1000 元/月 = 1K）；日薪/时薪/年薪等不可比口径返回 null。 */
export function monthlySalaryK(job: {
  low_salary: number | null
  salary_unit: string
}): number | null {
  if (job.low_salary == null) return null
  if (job.salary_unit === 'month_K') return job.low_salary
  if (job.salary_unit === 'month_yuan') return job.low_salary / 1000
  return null
}

export function expDisplay(job: {
  exp_min_years: number | null
  exp_max_years: number | null
  exp_text: string | null
}): string {
  if (job.exp_min_years == null && job.exp_max_years == null) return job.exp_text ?? '—'
  if (job.exp_min_years === 0 && job.exp_max_years === 0) return '不限'
  if (job.exp_min_years != null && job.exp_max_years == null) return `${job.exp_min_years}年以上`
  return `${job.exp_min_years ?? 0}-${job.exp_max_years}年`
}

export function degreeDisplay(job: { degree: string | null; degree_code: string | null }): string {
  if (job.degree_code) return DEGREE_LABEL[job.degree_code] ?? job.degree_code
  return job.degree ?? '—'
}