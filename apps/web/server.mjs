import { createReadStream } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
}

export function createSiteServer({
  root = '/site',
  apiUpstream = 'http://api:8000',
  apiToken,
  apiTokenFile,
  publicMode = false,
  accountMode = true,
} = {}) {
  return createServer(async (request, response) => {
    const requestUrl = new URL(request.url ?? '/', 'http://127.0.0.1')
    const urlPath = requestUrl.pathname
    if (urlPath.startsWith('/api/')) {
      const accountPath = urlPath.startsWith('/api/auth/') || urlPath === '/api/me' || urlPath.startsWith('/api/me/')
      if (publicMode && !accountPath && urlPath !== '/api/healthz') {
        response.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ code: 'LOCAL_ONLY' }))
        return
      }
      try {
        const requestChunks = []
        for await (const chunk of request) requestChunks.push(chunk)
        const requestBody = Buffer.concat(requestChunks)
        const proxyHeaders = new Headers()
        const requestContentType = request.headers['content-type']
        if (requestContentType) proxyHeaders.set('content-type', requestContentType)
        for (const headerName of ['cookie', 'origin', 'x-csrf-token']) {
          const value = request.headers[headerName]
          if (typeof value === 'string') proxyHeaders.set(headerName, value)
        }
        const isHealth = urlPath === '/api/healthz'
        if (accountMode && !isHealth && !accountPath) {
          const checkHeaders = new Headers()
          for (const headerName of ['cookie', 'origin', 'x-csrf-token']) {
            const value = request.headers[headerName]
            if (typeof value === 'string') checkHeaders.set(headerName, value)
          }
          const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method ?? 'GET')
          const checkPath = unsafe ? '/api/v1/auth/session-check' : '/api/v1/me'
          const check = await fetch(new URL(checkPath, apiUpstream), {
            method: unsafe ? 'POST' : 'GET',
            headers: checkHeaders,
          })
          if (!check.ok) {
            response.writeHead(check.status === 401 ? 401 : 403, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ code: 'ACCOUNT_FORBIDDEN' }))
            return
          }
          if (!unsafe) {
            const subject = await check.json().catch(() => null)
            if (subject?.is_admin !== true) {
              response.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' })
              response.end(JSON.stringify({ code: 'ACCOUNT_FORBIDDEN' }))
              return
            }
          }
        }
        if (!isHealth && !accountPath) {
          const token = apiToken ?? (apiTokenFile ? (await readFile(apiTokenFile, 'utf8')).trim() : '')
          if (!token) {
            response.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ code: 'PAIRING_TOKEN_UNAVAILABLE' }))
            return
          }
          proxyHeaders.set('authorization', `Bearer ${token}`)
        }
        // Query strings (limit/offset/status filters) must reach the API.
        const upstreamPath = isHealth
          ? `/healthz${requestUrl.search}`
          : `/api/v1${urlPath.slice(4)}${requestUrl.search}`
        const upstream = await fetch(new URL(upstreamPath, apiUpstream), {
          method: request.method,
          headers: proxyHeaders,
          body: requestBody.length ? requestBody : undefined,
        })
        const body = Buffer.from(await upstream.arrayBuffer())
        const responseHeaders = {
          'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
          'X-Content-Type-Options': 'nosniff',
        }
        const cookies = upstream.headers.getSetCookie?.() ?? []
        if (cookies.length) responseHeaders['Set-Cookie'] = cookies
        response.writeHead(upstream.status, responseHeaders)
        response.end(body)
      } catch {
        response.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
        response.end(JSON.stringify({ code: 'API_UNAVAILABLE' }))
      }
      return
    }

    const requested = resolve(root, `.${urlPath === '/' ? '/index.html' : urlPath}`)
    if (!requested.startsWith(`${root}/`)) {
      response.writeHead(400).end('Invalid path')
      return
    }

    let filePath = requested
    try {
      if (!(await stat(filePath)).isFile()) throw new Error('Not a file')
    } catch {
      filePath = resolve(root, 'index.html')
    }

    const contentType = contentTypes[extname(filePath)] ?? 'application/octet-stream'
    response.writeHead(200, { 'Content-Type': contentType, 'X-Content-Type-Options': 'nosniff' })
    createReadStream(filePath).pipe(response)
  })
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  createSiteServer({
    apiUpstream: process.env.API_UPSTREAM,
    apiToken: process.env.PAIRING_TOKEN,
    apiTokenFile: process.env.PAIRING_TOKEN_FILE,
    publicMode: process.env.PUBLIC_MODE === 'true',
  }).listen(4173, '0.0.0.0')
}
