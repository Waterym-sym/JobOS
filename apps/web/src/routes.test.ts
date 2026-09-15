import { describe, expect, it } from 'vitest'

import { flowRoutes, resolveRoute, routes, utilityRoutes } from './routes'

describe('console page map', () => {
  it('exposes the desk plus every architecture page-map area', () => {
    expect(routes.map((route) => route.path)).toEqual([
      '/', '/capture', '/jobs', '/shortlist', '/packages', '/events',
      '/retrospective', '/templates', '/knowledge', '/settings',
    ])
  })

  it('keeps the seven-step funnel separate from utility pages', () => {
    expect(flowRoutes).toHaveLength(7)
    expect(utilityRoutes.map((route) => route.path)).toEqual(['/templates', '/knowledge', '/settings'])
  })

  it('resolves direct hash routes and safely falls back to the desk', () => {
    expect(resolveRoute('#/capture').path).toBe('/capture')
    expect(resolveRoute('#/jobs?view=rejected').path).toBe('/jobs')
    expect(resolveRoute('#/unknown').path).toBe('/')
  })

  it('does not provide a direct package-creation action outside the shortlist', () => {
    expect(routes.filter((route) => route.nextPath === '/packages')).toEqual([])
  })
})
