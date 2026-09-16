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

  it('forwards POST method, body and content-type to the API', async () => {
    const api = createServer((request, response) => {
      const chunks = []
      request.on('data', (chunk) => chunks.push(chunk))
      request.on('end', () => {
        response.writeHead(202, { 'Content-Type': 'application/json' })
        response.end(
          JSON.stringify({
            method: request.method,
            url: request.url,
            contentType: request.headers['content-type'],
            authorization: request.headers.authorization,
            body: Buffer.concat(chunks).toString(),
          }),
        )
      })
    })
    const apiPort = await listen(api)
    const sitePort = await listen(
      createSiteServer({
        root: '/missing',
        apiUpstream: `http://127.0.0.1:${apiPort}`,
        apiToken: 'server-only-token',
      }),
    )

    const response = await fetch(`http://127.0.0.1:${sitePort}/api/captures`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'list', delay_ms: 1800 }),
    })

    expect(response.status).toBe(202)
    await expect(response.json()).resolves.toMatchObject({
      method: 'POST',
      url: '/api/v1/captures',
      contentType: 'application/json',
      authorization: 'Bearer server-only-token',
      body: JSON.stringify({ kind: 'list', delay_ms: 1800 }),
    })
  })

  it('forwards the query string so list filters reach the API', async () => {
    const api = createServer((request, response) => {
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ url: request.url }))
    })
    const apiPort = await listen(api)
    const sitePort = await listen(
      createSiteServer({
        root: '/missing',
        apiUpstream: `http://127.0.0.1:${apiPort}`,
        apiToken: 'server-only-token',
      }),
    )

    const response = await fetch(
      `http://127.0.0.1:${sitePort}/api/screening-entries?status=candidate&limit=20`,
    )

    await expect(response.json()).resolves.toEqual({
      url: '/api/v1/screening-entries?status=candidate&limit=20',
    })
  })

  it('does not accept a browser-supplied token when server credentials are absent', async () => {
    const sitePort = await listen(createSiteServer({ root: '/missing' }))
    const response = await fetch(`http://127.0.0.1:${sitePort}/api/captures`, {
      headers: { Authorization: 'Bearer browser-token' },
    })
    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toEqual({ code: 'PAIRING_TOKEN_UNAVAILABLE' })
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
