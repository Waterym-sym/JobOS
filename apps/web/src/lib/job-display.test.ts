import { describe, expect, it } from 'vitest'

import { monthlySalaryK } from './job-display'

describe('monthlySalaryK', () => {
  it('K·月 口径直接返回下限', () => {
    expect(monthlySalaryK({ low_salary: 10, salary_unit: 'month_K' })).toBe(10)
  })

  it('元·月 口径换算为 K', () => {
    expect(monthlySalaryK({ low_salary: 10000, salary_unit: 'month_yuan' })).toBe(10)
  })

  it('日薪/时薪等非月薪口径返回 null', () => {
    expect(monthlySalaryK({ low_salary: 250, salary_unit: 'day' })).toBeNull()
    expect(monthlySalaryK({ low_salary: 50, salary_unit: 'hour' })).toBeNull()
  })

  it('缺少下限返回 null', () => {
    expect(monthlySalaryK({ low_salary: null, salary_unit: 'month_K' })).toBeNull()
  })
})
