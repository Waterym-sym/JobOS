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
} = {}) {
  return createServer(async (request, response) => {
    const urlPath = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
    if (urlPath.startsWith('/api/')) {
      try {
        const requestChunks = []
        for await (const chunk of request) requestChunks.push(chunk)
        const requestBody = Buffer.concat(requestChunks)
        const proxyHeaders = new Headers()
        const requestContentType = request.headers['content-type']
        if (requestContentType) proxyHeaders.set('content-type', requestContentType)
        const isHealth = urlPath === '/api/healthz'
        if (!isHealth) {
          const token = apiToken ?? (apiTokenFile ? (await readFile(apiTokenFile, 'utf8')).trim() : '')
          if (!token) {
            response.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
            response.end(JSON.stringify({ code: 'PAIRING_TOKEN_UNAVAILABLE' }))
            return
          }
          proxyHeaders.set('authorization', `Bearer ${token}`)
        }
        const upstreamPath = isHealth ? '/healthz' : `/api/v1${urlPath.slice(4)}`
        const upstream = await fetch(new URL(upstreamPath, apiUpstream), {
          method: request.method,
          headers: proxyHeaders,
          body: requestBody.length ? requestBody : undefined,
        })
        const body = Buffer.from(await upstream.arrayBuffer())
        response.writeHead(upstream.status, {
          'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
          'X-Content-Type-Options': 'nosniff',
        })
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
  }).listen(4173, '0.0.0.0')
}
