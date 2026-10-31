import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { chromium, expect } from '@playwright/test'

const { values } = parseArgs({ options: { url: { type: 'string' }, out: { type: 'string' } } })
assert.ok(values.url && values.out, 'use --url LOOPBACK_URL --out EXTERNAL_EVIDENCE_DIRECTORY')
const base = new URL(values.url)
assert.equal(base.protocol, 'http:')
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname), 'fixture host must be loopback')
const api = '/api/terminal'
const headers = { Origin: base.origin, 'Content-Type': 'application/json', 'X-Copilot-Terminal': '1' }
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
const observations = []
page.on('pageerror', error => errors.push(error.message))
const text = () => page.locator('.copilot-terminal .xterm-accessibility-tree').innerText()
const storage = () => page.evaluate(prefix => JSON.parse(sessionStorage.getItem(`copilot-terminal:${prefix}`) ?? 'null'), api)
let session = null

try {
  await mkdir(values.out, { recursive: true })
  await page.goto(base.href, { waitUntil: 'domcontentloaded' })
  await expect(page.getByText('PTY fixture', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start Copilot', exact: true })).toBeEnabled({ timeout: 10000 })
  await page.getByRole('button', { name: 'Start Copilot', exact: true }).click()
  await expect(page.locator('.copilot-terminal')).toHaveAttribute('data-state', 'Connected')
  await expect.poll(text).toContain('PTY transport fixture')
  session = await storage()
  assert.ok(session)

  await page.getByLabel('Insert CLI command', { exact: true }).click()
  const help = page.getByTitle('Insert /help', { exact: true })
  await expect(help).toBeEnabled()
  await help.click()
  await expect.poll(text).toContain('/help')
  assert.ok(!(await text()).includes('Fixture received: /help'), 'menu must not submit automatically')
  await page.keyboard.press('Enter')
  await expect.poll(text).toContain('Fixture received: /help')
  observations.push('native command insertion waits for user submission')

  await page.getByRole('button', { name: 'Inspect source', exact: true }).click()
  await expect.poll(text, { timeout: 10000 }).toContain('Fixture received: Inspect the local example source without modifying it.')
  observations.push('prepared host action reaches the real PTY')

  await page.getByRole('button', { name: 'Use selected file in terminal', exact: true }).click()
  await expect.poll(text).toContain('sources/example.txt')
  assert.equal(await readFile(resolve(session.workspace, 'sources/example.txt'), 'utf8'), 'Local example source. No remote dataset.\n')
  await page.keyboard.press('Enter')
  await expect.poll(text).toContain('Fixture received: @')
  observations.push('selected source is staged and read back from the private workspace')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('.copilot-terminal')).toHaveAttribute('data-state', 'Connected')
  assert.equal((await storage()).session_id, session.session_id)
  await expect.poll(text).toContain('Fixture received: /help')
  observations.push('reload reconnects with bounded output replay')

  for (const [name, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height })
    await expect.poll(() => page.locator('.copilot-terminal-host').evaluate(element => element.clientWidth)).toBeGreaterThan(200)
    const geometry = await page.locator('.copilot-terminal').evaluate(element => {
      const bounds = element.getBoundingClientRect()
      return { left: bounds.left, right: bounds.right, bottom: bounds.bottom, width: bounds.width,
        overflow: document.documentElement.scrollWidth > innerWidth }
    })
    assert.equal(geometry.overflow, false)
    assert.ok(geometry.left >= 0 && geometry.right <= width + 1 && geometry.bottom <= height + 1)
    await page.getByLabel('Insert CLI command', { exact: true }).click()
    const menu = await page.locator('.copilot-terminal-command-list').boundingBox()
    assert.ok(menu && menu.x >= 0 && menu.x + menu.width <= width + 1, 'command menu must remain inside viewport')
    await page.screenshot({ path: resolve(values.out, `${name}.png`) })
    await page.getByLabel('Insert CLI command', { exact: true }).press('Escape')
    observations.push({ viewport: name, width, height, geometry })
  }

  for (const [action, changed, status] of [['input', { key: 'wrong', data: 'unwanted' }, 404],
    ['source', { source: { uid: 'other', path: '../private' } }, 404]]) {
    const result = await page.request.post(new URL(`${api}/${action}`, base).href, { headers, data: { ...session, ...changed } })
    assert.equal(result.status(), status)
  }
  assert.equal((await page.request.post(new URL(`${api}/start`, base).href, {
    headers: { ...headers, Origin: 'https://untrusted.example' }, data: {},
  })).status(), 403)
  assert.equal((await page.request.post(new URL(`${api}/start`, base).href, {
    headers, data: { mode: 'autopilot' },
  })).status(), 400)
  observations.push('wrong session, unapproved source, cross-origin and browser launch override refused')

  await page.getByRole('button', { name: 'Interrupt current command', exact: true }).click()
  await expect.poll(text).toContain('Fixture interrupt received')
  await page.getByRole('button', { name: 'End terminal session', exact: true }).click()
  await expect(page.locator('.copilot-terminal')).toHaveAttribute('data-state', 'Disconnected')
  assert.equal((await page.request.post(new URL(`${api}/output`, base).href, { headers, data: { ...session, cursor: 0 } })).status(), 404)
  session = null
  assert.deepEqual(errors, [])
  observations.push('interrupt delivered, Stop revokes ownership, no browser exceptions')
  await writeFile(resolve(values.out, 'result.json'), JSON.stringify({ passed: true, model_calls: false, transport: 'fixture', observations }, null, 2))
  console.log('PASS: real browser/PTY, command insertion, host action, source read-back, reconnect, responsive geometry and authorization refusals; no model call')
} finally {
  if (session) await page.request.post(new URL(`${api}/stop`, base).href, { headers, data: session }).catch(() => {})
  await browser.close()
}