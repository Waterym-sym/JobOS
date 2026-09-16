import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

type Manifest = {
  manifest_version: number
  permissions?: string[]
  host_permissions?: string[]
  content_scripts?: unknown[]
  options_page?: string
  content_security_policy?: { extension_pages?: string }
}

const manifest = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../public/manifest.json'), 'utf8'),
) as Manifest

describe('extension manifest safety baseline', () => {
  it('limits site access to BOSS pages only', () => {
    expect(manifest.manifest_version).toBe(3)
    // Site access is exactly the BOSS host: no <all_urls>, no wildcards.
    expect(manifest.host_permissions).toEqual(['https://www.zhipin.com/*'])
    // Data collection happens through injected reads, not declared content scripts.
    expect(manifest.content_scripts ?? []).toEqual([])
  })

  it('requests storage plus the tab/scripting/alarm permissions capture needs', () => {
    expect(manifest.permissions).toEqual(['storage', 'scripting', 'tabs', 'alarms'])
  })

  it('exposes a local-only pairing page without remote script access', () => {
    expect(manifest.options_page).toBe('options.html')
    expect(manifest.content_security_policy?.extension_pages).toContain(
      'connect-src ws://127.0.0.1:8788',
    )
    expect(manifest.content_security_policy?.extension_pages).toContain("script-src 'self'")
  })
})