import { describe, expect, it } from 'vitest'

import { flowRoutes, resolveRoute, routes, settingsRoutes } from './routes'

describe('console page map', () => {
  it('keeps the funnel routes intact', () => {
    expect(flowRoutes.map((route) => route.path)).toEqual([
      '/', '/capture', '/jobs', '/screening', '/shortlist', '/packages', '/events',
      '/retrospective',
    ])
  })

  it('exposes the settings group with all sub-pages', () => {
    expect(settingsRoutes.map((route) => route.path)).toEqual([
      '/settings', '/settings/model', '/settings/local', '/settings/extension',
      '/settings/theme', '/settings/knowledge', '/settings/resume', '/settings/privacy',
    ])
  })

  it('includes the login route', () => {
    expect(routes.some((route) => route.path === '/login')).toBe(true)
  })

  it('resolves direct hash routes and safely falls back to the desk', () => {
    expect(resolveRoute('#/capture').path).toBe('/capture')
    expect(resolveRoute('#/screening').path).toBe('/screening')
    expect(resolveRoute('#/jobs?view=rejected').path).toBe('/jobs')
    expect(resolveRoute('#/unknown').path).toBe('/')
  })

  it('resolves settings sub-paths back to the account settings hub', () => {
    expect(resolveRoute('#/settings/model').path).toBe('/settings/model')
    expect(resolveRoute('#/settings/unknown-sub').path).toBe('/settings')
  })

  it('does not provide a direct package-creation action outside the shortlist', () => {
    expect(routes.filter((route) => route.nextPath === '/packages')).toEqual([])
  })
})
