/**
 * Local-only bridge service worker.
 *
 * Connection + command dispatch wiring only; the socket lives in ws-client.ts
 * and command execution in commands.ts.
 */

import { handleCommand } from './commands'
import { DEFAULT_WS_URL } from './protocol'
import { connectOnce, isConnected, setCommandHandler } from './ws-client'

const RECONNECT_ALARM = 'jobos-reconnect'

setCommandHandler(handleCommand)

// MV3 service workers are recycled; alarms are the only reliable way to come
// back without user interaction.
chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 1 })
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RECONNECT_ALARM && !isConnected()) void connectOnce()
})

chrome.runtime.onInstalled.addListener(() => {
  void chrome.storage.local
    .get('ws_url')
    .then((stored) => {
      if (stored.ws_url === undefined) return chrome.storage.local.set({ ws_url: DEFAULT_WS_URL })
      return undefined
    })
    .then(connectOnce)
})

chrome.runtime.onStartup.addListener(() => {
  void connectOnce()
})

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local' && (changes.ws_url || changes.pairing_token)) {
    void connectOnce()
  }
})

void connectOnce()