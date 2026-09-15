import { createServer } from 'node:http'

import { afterEach, describe, expect, it } from 'vitest'

import { createSiteServer } from '../server.mjs'

const servers = []

function listen(server) {
  servers.push(server)
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve(server.address().port))
  })
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => new Promise((resolve) => server.close(resolve))))
})

describe('site server', () => {
  it('proxies the local health endpoint', async () => {
    const api = createServer((_request, response) => {
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ service: 'api', status: 'ok' }))
    })
    const apiPort = await listen(api)
    const sitePort = await listen(
      createSiteServer({ root: '/missing', apiUpstream: `http://127.0.0.1:${apiPort}` }),
    )

    const response = await fetch(`http://127.0.0.1:${sitePort}/api/healthz`)
    await expect(response.json()).resolves.toMatchObject({ service: 'api', status: 'ok' })
  })

  it('returns a structured gateway error when the API is unavailable', async () => {
    const sitePort = await listen(
      createSiteServer({ root: '/missing', apiUpstream: 'http://127.0.0.1:1' }),
    )
    const response = await fetch(`http://127.0.0.1:${sitePort}/api/healthz`)

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toEqual({ code: 'API_UNAVAILABLE' })
  })
})
