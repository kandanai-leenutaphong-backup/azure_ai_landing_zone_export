import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { chromium, expect } from '@playwright/test'

const { values } = parseArgs({ options: { url: { type: 'string' }, out: { type: 'string' } } })
assert.ok(values.url && values.out, 'use --url LOOPBACK_URL --out EXTERNAL_EVIDENCE_DIRECTORY')
const base = new URL(values.url)
assert.equal(base.protocol, 'http:')
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname))
const browser = await chromium.launch()
const observations = []

try {
  await mkdir(values.out, { recursive: true })
  for (const unknownDialog of [false, true]) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const inputs = []
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/terminal/input') inputs.push(request.postDataJSON().data)
    })
    if (unknownDialog) {
      await page.route('**/api/terminal/output', async route => {
        const response = await route.fetch()
        const payload = await response.json()
        payload.output = payload.output?.replaceAll('Continue with limited permissions', 'Unknown fixture permission choice')
        await route.fulfill({ response, json: payload })
      })
    }
    try {
      await page.goto(base.href, { waitUntil: 'domcontentloaded' })
      await expect(page.getByText('Offline CLI', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Start Copilot', exact: true }).click()
      const action = page.getByRole('button', { name: 'Autopilot session', exact: true })
      await expect(action).toBeEnabled({ timeout: 60000 })
      await action.click()
      if (unknownDialog) {
        await expect(page.getByRole('alert')).toContainText('Unknown autopilot permission dialog', { timeout: 30000 })
        assert.ok(!inputs.includes('/session info'), 'unknown dialog must not receive the prepared action')
        assert.ok(!inputs.includes('\x1b[B'), 'unknown dialog must not receive a permission selection')
      } else {
        const screen = () => page.locator('.copilot-terminal .xterm-accessibility-tree').innerText()
        const actionInputs = () => inputs.filter(data => data.startsWith('/') || ['\r', '\x1b[B', '\x1b[A'].includes(data))
        await expect.poll(actionInputs, { timeout: 40000 }).toEqual([
          '/settings stayInAutopilot false', '\r', '/autopilot on', '\r', '\x1b[B', '\r', '/session info', '\r',
        ])
        await expect.poll(screen).toMatch(/session\s+id:/i)
        await expect(page.getByRole('alert')).toHaveCount(0)
        for (const [name, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]]) {
          await page.setViewportSize({ width, height })
          await expect.poll(() => page.locator('.copilot-terminal-host').evaluate(element => element.clientWidth)).toBeGreaterThan(200)
          const bounds = await page.locator('.copilot-terminal').boundingBox()
          assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1 && bounds.y + bounds.height <= height + 1)
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
          await page.screenshot({ path: resolve(values.out, `autopilot-${name}.png`) })
        }
      }
      assert.deepEqual(errors, [])
      observations.push(unknownDialog ? 'unknown permission dialog refused before action or selection' : 'native limited-permission transition and session command completed')
    } finally {
      if (await page.getByRole('button', { name: 'End terminal session', exact: true }).count()) {
        await page.getByRole('button', { name: 'End terminal session', exact: true }).click()
        await expect(page.locator('.copilot-terminal')).toHaveAttribute('data-state', 'Disconnected')
      }
      await page.close()
    }
  }
  await writeFile(resolve(values.out, 'autopilot-result.json'), JSON.stringify({ passed: true, model_calls: false, observations }, null, 2))
  console.log('PASS: real native limited autopilot and unknown-dialog refusal; no inference prompt')
} finally {
  await browser.close()
}