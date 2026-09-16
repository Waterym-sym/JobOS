import { describe, expect, it } from 'vitest'

import { flowRoutes, resolveRoute, routes, utilityRoutes } from './routes'

describe('console page map', () => {
  it('exposes the desk plus every architecture page-map area', () => {
    expect(routes.map((route) => route.path)).toEqual([
      '/', '/capture', '/jobs', '/screening', '/shortlist', '/packages', '/events',
      '/retrospective', '/templates', '/knowledge', '/settings',
    ])
  })

  it('keeps the funnel separate from utility pages', () => {
    // 页面地图随 P1-005 把「岗位池与筛选」拆为「岗位池」+「筛选池」（8 级）。
    expect(flowRoutes).toHaveLength(8)
    expect(utilityRoutes.map((route) => route.path)).toEqual(['/templates', '/knowledge', '/settings'])
  })

  it('resolves direct hash routes and safely falls back to the desk', () => {
    expect(resolveRoute('#/capture').path).toBe('/capture')
    expect(resolveRoute('#/screening').path).toBe('/screening')
    expect(resolveRoute('#/jobs?view=rejected').path).toBe('/jobs')
    expect(resolveRoute('#/unknown').path).toBe('/')
  })

  it('does not provide a direct package-creation action outside the shortlist', () => {
    expect(routes.filter((route) => route.nextPath === '/packages')).toEqual([])
  })
})
